import asyncio
import base64
import json
import logging
from fastapi import HTTPException, Request, status, UploadFile
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from app.schemas.attendance import Attendance
from app.utils.publisher import send_to_queue
from app.utils.redis_pub_sub import subscribe_to_channel
from redis.exceptions import ConnectionError, TimeoutError
from typing import List

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def recognize_students(request: Request, attendance_id: str,images: List[UploadFile]):
    

    # 1️⃣ Verify role
    if request.state.user.get("role") != "teacher":
        # logger.error(f"[recognize_students] Unauthorized access attempt for attendance_id: {attendance_id}, role: {user_data.get('role')}")
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "Only teachers can perform face recognition."
            }
        )
       
    logger.info(f"[recognize_students] User role verified as teacher for attendance_id: {attendance_id}")

    # 2️⃣ Fetch attendance and linked session details
    attendance = await Attendance.get(attendance_id, fetch_links=True)
    if not attendance:
        logger.error(f"[recognize_students] Attendance record not found for attendance_id: {attendance_id}")
        
        
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": "Attendance record not found."
            }
        )
        
    logger.info(f"[recognize_students] Successfully fetched attendance record for attendance_id: {attendance_id}")

    semester = attendance.session.semester
    department = attendance.session.department
    program = attendance.session.program
    academic_year = attendance.session.academic_year

    # 3️⃣ Read and encode all uploaded images to base64
    image_base64_list = []
    for idx, image in enumerate(images):
        if not image.content_type.startswith("image/"):
            
            return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": f"File '{image.filename}' must be an image."
            }
        )
            
            
        image_bytes = await image.read()
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        image_base64_list.append(image_base64)

    if not image_base64_list:

        
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "At least one image is required."
            }
        )

    # 4️⃣ Add the recognition job to the queue with multiple images
    job_data = {
        "type": "recognize_faces",
        "data": {
            "attendance_id": attendance_id,
            "image_base64_list": image_base64_list,
            "semester": semester,
            "department": department,
            "program": program,
            "academic_year": academic_year
        }
    }
    await send_to_queue("face_recog_queue", job_data, priority=10)

    # 5️⃣ Define the generator to stream updates
    async def event_generator():
        progress_channel = f"face_progress:{attendance_id}"
        recognized_channel = f"student_recognized:{attendance_id}"
        logger.info(f"[event_generator] Subscribing to Redis channels: {progress_channel}, {recognized_channel}")

        try:
            async with subscribe_to_channel(progress_channel) as pubsub:
                # Manually subscribe to the second channel
                await pubsub.subscribe(recognized_channel)

                while True:
                    try:
                        message = await asyncio.wait_for(
                            pubsub.get_message(ignore_subscribe_messages=True),
                            timeout=300.0
                        )

                        if not message:
                            continue

                        raw_data = message["data"]
                        channel = message.get("channel", "").decode("utf-8") if isinstance(message.get("channel"), bytes) else message.get("channel")

                        if not raw_data or raw_data.strip() == "":
                            continue

                        try:
                            data = json.loads(raw_data)

                            # Handle student recognition events
                            if channel == recognized_channel:
                                yield json.dumps({
                                    "event": "student_recognized",
                                    **data
                                })
                                continue

                            # Handle progress events
                            if data.get("status") == "complete":
                                annotated_image = data.get("annotated_image_base64")
                                if annotated_image:
                                    yield json.dumps({
                                        "status": "final_image",
                                        "image_base64": annotated_image,
                                        "message": data.get("message", "Recognition complete")
                                    })
                                else:
                                    yield json.dumps({
                                        "status": "complete",
                                        "message": data.get("message", "Recognition complete")
                                    })
                                break

                            elif data.get("status") == "failed":
                                yield json.dumps({
                                    "status": "failed",
                                    "reason": data.get("reason", "Unknown error")
                                })
                                break

                            else:
                                yield json.dumps(data)

                        except json.JSONDecodeError as e:
                            yield json.dumps({
                                "status": "failed",
                                "reason": f"Invalid message format: {str(e)}"
                            })
                            break

                    except asyncio.TimeoutError:
                        yield json.dumps({
                            "status": "failed",
                            "reason": "Processing timed out."
                        })
                        break

        except (ConnectionError, TimeoutError) as e:
            yield json.dumps({
                "status": "failed",
                "reason": f"Cannot connect to Redis: {str(e)}"
            })

    # Return SSE response
    return EventSourceResponse(event_generator())
