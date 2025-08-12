import asyncio
import base64
import io
import json
from fastapi import HTTPException, status, UploadFile
from starlette.responses import StreamingResponse
from app.schemas.attendance import Attendance
from app.utils.publisher import send_to_queue
from app.utils.redis_pub_sub import subscribe_to_channel
import logging
from redis.exceptions import ConnectionError, TimeoutError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def recognize_students(attendance_id: str, user_data: dict, image: UploadFile):
    # 1️⃣ Verify role
    if user_data.get("role") != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can perform face recognition."
        )

    # 2️⃣ Fetch attendance and linked session details
    attendance = await Attendance.get(attendance_id, fetch_links=True)
    if not attendance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance record not found."
        )

    semester = attendance.session.semester
    department = attendance.session.department
    program = attendance.session.program

    # 3️⃣ Read and encode the uploaded image to base64
    image_bytes = await image.read()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    # 4️⃣ Add the recognition job to the queue
    await send_to_queue(
        "face_recog_queue",
        {
            "type": "recognize_faces",
            "data": {
                "attendance_id": attendance_id,
                "image_base64": image_base64,
                "semester": semester,
                "department": department,
                "program": program
            }
        },
        priority=10  # High priority for recognition
    )

    # 5️⃣ Subscribe to Redis channel to wait for the annotated image
    channel_name = f"face_progress:{attendance_id}"
    logger.info(f"[recognize_students] Subscribing to Redis channel: {channel_name}")

    async def wait_for_annotated_image():
        try:
            async with subscribe_to_channel(channel_name) as pubsub:
                async for message in pubsub.listen():
                    try:
                        if message["type"] != "message":
                            logger.debug(f"[wait_for_annotated_image] Skipping non-message event: {message}")
                            continue
                        message_data = message["data"]
                        if isinstance(message_data, bytes):
                            message_data = message_data.decode("utf-8")
                        data = json.loads(message_data)
                        logger.debug(f"[wait_for_annotated_image] Received message: {data}")
                        if data.get("status") == "complete" and "annotated_image" in data:
                            annotated_image_bytes = base64.b64decode(data["annotated_image"])
                            return annotated_image_bytes, data.get("results", [])
                        elif data.get("status") == "failed":
                            raise HTTPException(
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail=f"Face recognition failed: {data.get('reason')}"
                            )
                    except json.JSONDecodeError as e:
                        logger.error(f"[wait_for_annotated_image] Invalid JSON in message: {message_data}, error: {str(e)}")
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Invalid message format: {str(e)}"
                        )
                    except Exception as e:
                        logger.error(f"[wait_for_annotated_image] Error processing Redis message: {str(e)}")
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Error processing face recognition: {str(e)}"
                        )
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"[wait_for_annotated_image] Redis connection error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Cannot connect to Redis: {str(e)}"
            )

    # 6️⃣ Wait for the result with a timeout
    try:
        annotated_image_bytes, results = await asyncio.wait_for(wait_for_annotated_image(), timeout=120.0)
    except asyncio.TimeoutError:
        logger.error(f"[recognize_students] Timeout waiting for face recognition result for attendance_id: {attendance_id}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Face recognition processing timed out."
        )
    except HTTPException as e:
        raise e

    # 7️⃣ Return the annotated image as a StreamingResponse
    logger.info(f"[recognize_students] Returning annotated image for attendance_id: {attendance_id}")
    return StreamingResponse(
        io.BytesIO(annotated_image_bytes),
        media_type="image/jpeg",
        headers={
            "X-Face-Recognition-Results": json.dumps(results)
        }
    )