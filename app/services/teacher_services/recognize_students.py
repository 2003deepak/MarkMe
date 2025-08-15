import asyncio
import base64
import io
import json
import logging
from fastapi import HTTPException, status, UploadFile
from sse_starlette.sse import EventSourceResponse
from app.schemas.attendance import Attendance
from app.utils.publisher import send_to_queue
from app.utils.redis_pub_sub import subscribe_to_channel
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

    # 5️⃣ Define the generator to stream updates
    async def event_generator():
        channel_name = f"face_progress:{attendance_id}"
        logger.info(f"[recognize_students] Subscribing to Redis channel for streaming: {channel_name}")
        try:
            async with subscribe_to_channel(channel_name) as pubsub:
                while True:
                    try:
                        message = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True), timeout=300.0)
                        if message:
                            data = json.loads(message["data"])

                            # logger.info(f"[event_generator] Received message: {data}")

                            # SSE protocol: send a chunk of progress (or final image) to client
                            if data.get("status") == "complete":
                                # Send the final annotated image if included
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
                                # Send failure info
                                yield json.dumps({
                                    "status": "failed",
                                    "reason": data.get("reason", "Unknown error"),
                                })
                                break
                            else:
                                # Progress update (streamed chunk)
                                yield json.dumps(data)

                    except asyncio.TimeoutError:
                        logger.warning(f"[event_generator] Timeout waiting for Redis message on channel: {channel_name}. Closing connection.")
                        yield json.dumps({"status": "failed", "reason": "Processing timed out."})
                        break
                    except json.JSONDecodeError as e:
                        logger.error(f"[event_generator] Invalid JSON in message: {message['data']}, error: {str(e)}")
                        yield json.dumps({"status": "failed", "reason": f"Invalid message format: {str(e)}"})
                        break

        except (ConnectionError, TimeoutError) as e:
            logger.error(f"[recognize_students] Redis connection error: {str(e)}")
            yield json.dumps({"status": "failed", "reason": f"Cannot connect to Redis: {str(e)}"})

    # Return SSE, streaming updates and the final annotated image
    return EventSourceResponse(event_generator())
