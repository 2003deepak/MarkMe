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


async def recognize_students(request: Request, attendance_id: str, images: List[UploadFile]):
    logger.info(f"[recognize_students] Received request for attendance_id={attendance_id}")

    # -------------------------------------------------------------
    # 1️⃣ Verify teacher role
    # -------------------------------------------------------------
    user_role = request.state.user.get("role")
    if user_role != "teacher":
        logger.warning(f"[recognize_students] Unauthorized role '{user_role}' attempted access.")
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only teachers can perform face recognition."}
        )

    logger.info(f"[recognize_students] Role verified: teacher")

    # -------------------------------------------------------------
    # 2️⃣ Fetch attendance + session
    # -------------------------------------------------------------
    attendance = await Attendance.get(attendance_id, fetch_links=True)
    if not attendance:
        logger.error(f"[recognize_students] Attendance NOT FOUND for id={attendance_id}")
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Attendance record not found."}
        )

    logger.info(f"[recognize_students] Attendance found for id={attendance_id}")

    # Handle normal or exception session
    if attendance.session:
        session_obj = attendance.session
        logger.info("[recognize_students] Using normal session")
    elif attendance.exception_session:
        if not attendance.exception_session.session:
            logger.error("[recognize_students] Exception session missing base session")
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "Exception session has no linked base session."}
            )
        session_obj = attendance.exception_session.session
        logger.info("[recognize_students] Using exception session")
    else:
        logger.error("[recognize_students] No session or exception session found")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Attendance has no valid session."}
        )

    # Extract meta data
    semester = session_obj.semester
    department = session_obj.department
    program = session_obj.program
    academic_year = session_obj.academic_year

    # -------------------------------------------------------------
    # 3️⃣ Convert uploaded images → Base64
    # -------------------------------------------------------------
    image_base64_list = []
    for idx, image in enumerate(images):
        logger.info(f"[recognize_students] Processing uploaded file: {image.filename}")

        if not image.content_type.startswith("image/"):
            logger.warning(f"[recognize_students] Invalid file type: {image.filename}")
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": f"File '{image.filename}' must be an image."}
            )

        image_bytes = await image.read()
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        image_base64_list.append(image_base64)

    if not image_base64_list:
        logger.warning("[recognize_students] No images received")
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "At least one image is required."}
        )

    logger.info(f"[recognize_students] Total images received: {len(image_base64_list)}")

    # -------------------------------------------------------------
    # 4️⃣ Add job into RabbitMQ queue
    # -------------------------------------------------------------
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

    logger.info(f"[recognize_students] Sending job to face_recog_queue for attendance_id={attendance_id}")
    await send_to_queue("face_recog_queue", job_data, priority=10)

    # -------------------------------------------------------------
    # 5️⃣ SSE Streaming Generator
    # -------------------------------------------------------------
    async def event_generator():
        progress_channel = f"face_progress:{attendance_id}"
        recognized_channel = f"student_recognized:{attendance_id}"

        logger.info(f"[event_generator] Subscribing to Redis:")
        logger.info(f"  - Progress channel: {progress_channel}")
        logger.info(f"  - Recognition channel: {recognized_channel}")

        try:
            async with subscribe_to_channel(progress_channel) as pubsub:
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
                        channel_raw = message.get("channel")

                        channel = channel_raw.decode("utf-8") if isinstance(channel_raw, bytes) else channel_raw

                        logger.info(f"[event_generator] Message from channel={channel}: {raw_data}")

                        if not raw_data:
                            continue

                        # Convert JSON safely
                        data = json.loads(raw_data)

                        # ---------------------------------------------------------
                        # ⭐ ADD SLOWDOWN WHEN A FACE IS DETECTED ⭐
                        # ---------------------------------------------------------
                        if channel == recognized_channel:
                            logger.info(f"[event_generator] FACE DETECTED -> Delaying 2 seconds for UI testing")
                            await asyncio.sleep(1)

                            yield json.dumps({
                                "event": "student_recognized",
                                **data
                            })
                            continue

                        # ---------------------------------------------------------
                        # Progress events
                        # ---------------------------------------------------------
                        if data.get("status") == "complete":
                            logger.info("[event_generator] Recognition complete")
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
                            logger.error(f"[event_generator] Failure: {data}")
                            yield json.dumps({
                                "status": "failed",
                                "reason": data.get("reason", "Unknown error")
                            })
                            break

                        else:
                            yield json.dumps(data)

                    except asyncio.TimeoutError:
                        logger.error("[event_generator] Time out while waiting for Redis messages")
                        yield json.dumps({
                            "status": "failed",
                            "reason": "Processing timed out."
                        })
                        break

        except (ConnectionError, TimeoutError) as e:
            logger.error(f"[event_generator] Redis connection error: {e}")
            yield json.dumps({
                "status": "failed",
                "reason": f"Cannot connect to Redis: {str(e)}"
            })

    return EventSourceResponse(event_generator())
