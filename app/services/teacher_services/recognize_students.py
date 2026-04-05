import asyncio
import base64
import json
import logging
from fastapi import Request, UploadFile
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from app.schemas.attendance import Attendance
from app.utils.publisher import send_to_queue
from app.utils.redis_pub_sub import subscribe_to_channel
from redis.exceptions import ConnectionError, TimeoutError
from typing import List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def recognize_students(request: Request, attendance_id: str, images: List[UploadFile]):
    logger.info(f"[recognize_students] Received request for attendance_id={attendance_id}")

    #auth
    user_role = request.state.user.get("role")
    if user_role != "teacher":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only teachers can perform face recognition."}
        )

    #fetch attendance
    attendance = await Attendance.get(attendance_id, fetch_links=True)
    if not attendance:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Attendance record not found."}
        )

    #session resolve
    if attendance.session:
        session_obj = attendance.session
    elif attendance.exception_session and attendance.exception_session.session:
        session_obj = attendance.exception_session.session
    else:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Attendance has no valid session."}
        )

    semester = session_obj.semester
    department = session_obj.department
    program = session_obj.program
    academic_year = session_obj.academic_year

    #image processing
    image_base64_list = []

    MAX_SIZE = 5 * 1024 * 1024  # 5MB

    for image in images:
        if not image.content_type.startswith("image/"):
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": f"{image.filename} must be an image"}
            )

        image_bytes = await image.read()

        #size validation
        if len(image_bytes) > MAX_SIZE:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Image too large (max 5MB)"}
            )

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        image_base64_list.append(image_base64)

    if not image_base64_list:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "At least one image is required."}
        )

    logger.info(f"[recognize_students] Images received: {len(image_base64_list)}")

    #queue job
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

    #sse
    async def event_generator():
        progress_channel = f"face_progress:{attendance_id}"
        recognized_channel = f"student_recognized:{attendance_id}"

        try:
            async with subscribe_to_channel(progress_channel) as pubsub:
                await pubsub.subscribe(recognized_channel)

                #🔥 initial response (IMPORTANT)
                yield json.dumps({
                    "status": "started",
                    "message": "Processing started"
                })

                while True:
                    try:
                        message = await asyncio.wait_for(
                            pubsub.get_message(ignore_subscribe_messages=True),
                            timeout=300.0
                        )

                        if not message:
                            continue

                        data = json.loads(message["data"])
                        channel_raw = message.get("channel")
                        channel = channel_raw.decode() if isinstance(channel_raw, bytes) else channel_raw

                        if channel == recognized_channel:
                            yield json.dumps({
                                "event": "student_recognized",
                                **data
                            })
                            continue

                        if data.get("status") == "complete":
                            yield json.dumps(data)
                            break

                        elif data.get("status") == "failed":
                            yield json.dumps(data)
                            break

                        else:
                            yield json.dumps(data)

                    except asyncio.TimeoutError:
                        yield json.dumps({
                            "status": "failed",
                            "reason": "Processing timed out"
                        })
                        break

        except (ConnectionError, TimeoutError) as e:
            yield json.dumps({
                "status": "failed",
                "reason": str(e)
            })

    return EventSourceResponse(event_generator())