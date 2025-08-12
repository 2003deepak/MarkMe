import asyncio
import aio_pika
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bson import ObjectId
from pymongo.errors import PyMongoError
import logging

from app.schemas.session import Session
from app.schemas.subject import Subject
from app.schemas.attendance import Attendance
from app.schemas.exception_session import ExceptionSession
from app.core.rabbitmq_config import settings
from app.core.database import init_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def process_session(message: aio_pika.IncomingMessage):
    logger.info("⚙️ process_session triggered")

    async with message.process():
        try:
            payload = json.loads(message.body.decode())
            logger.info(f"📥 Received session payload:\n{json.dumps(payload, indent=2)}")

            # Validate required fields
            required_fields = [
                "session_id",
                "date",
                "start_time_timestamp",
                "subject"  # Ensure subject is required
            ]

            if not all(payload.get(field) is not None for field in required_fields):
                logger.error(f"❌ Invalid payload: Missing required fields: {required_fields}")
                return

            session_id = payload["session_id"]
            date = payload["date"]
            start_time_timestamp = payload["start_time_timestamp"]
            subject_id = payload["subject"]

            # Validate IDs
            try:
                session_obj_id = ObjectId(session_id)
                subject_id_obj = ObjectId(subject_id)
            except Exception as e:
                logger.error(f"❌ Invalid ObjectId format for session_id or subject_id: {e}")
                return

            # ⏳ Check if session is within 15 mins
            session_start = datetime.fromtimestamp(start_time_timestamp, tz=ZoneInfo("Asia/Kolkata"))
            now = datetime.now(tz=ZoneInfo("Asia/Kolkata"))

            if (session_start - now) > timedelta(minutes=15):
                logger.info(f"⏳ Skipping session, starts later than 15 min: {session_start}")
                return

            # 🎯 Fetch Session
            session = await Session.get(session_obj_id)
            if not session:
                logger.error(f"❌ Session not found: {session_id}")
                return

            # 🎯 Fetch Subject
            subject = await Subject.get(subject_id_obj)
            if not subject:
                logger.error(f"❌ Subject not found: {subject_id}")
                return

            # 🔁 Check for ExceptionSession
            try:
                exception = await ExceptionSession.find_one(
                    ExceptionSession.session == session_obj_id,
                    ExceptionSession.date == datetime.strptime(date, "%Y-%m-%d")
                )
            except PyMongoError as e:
                logger.error(f"❌ DB error during ExceptionSession lookup: {e}")
                return

            if exception:
                action = exception.action.lower()
                logger.info(f"⚠️ Exception found: {action}")

                if action == "cancelled":
                    logger.info(f"🚫 Cancelled session {session_id} on {date}")
                    return

                elif action == "rescheduled":
                    new_session_data = exception.new_slot.model_dump() if exception.new_slot else None
                    if not new_session_data:
                        logger.error("⚠️ Rescheduled session missing new_slot data")
                        return

                    new_start = datetime.strptime(
                        f"{date} {new_session_data['start_time']}", "%Y-%m-%d %H:%M"
                    ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

                    new_payload = {
                        **payload,
                        "start_time_timestamp": new_start.timestamp()
                    }

                    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
                    async with connection:
                        channel = await connection.channel()
                        await channel.default_exchange.publish(
                            aio_pika.Message(
                                body=json.dumps(new_payload).encode(),
                                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                            ),
                            routing_key=settings.session_queue
                        )
                    logger.info(f"🔁 Rescheduled session re-queued for {new_start}")
                    return

                elif action == "add":
                    logger.info("📌 Exception 'add' — proceeding to mark attendance.")

            # ✅ Store Attendance
            try:
                attendance = Attendance(
                    session=session_obj_id,
                    date=datetime.strptime(date, "%Y-%m-%d"),
                    day=payload.get("day"),
                    subject=subject_id_obj,
                    program=payload.get("program"),
                    department=payload.get("department"),
                    semester=payload.get("semester"),
                    academic_year=payload.get("academic_year"),
                    students=""
                )
                await attendance.insert()
                logger.info(f"✅ Stored attendance for session {session_id}")
                logger.info(f"📝 Attendance document: {attendance.model_dump_json(indent=2)}")

            except (ValueError, PyMongoError) as e:
                logger.error(f"❌ Failed to store attendance: {e}")

        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to decode payload: {e}")
        except ValueError as e:
            logger.error(f"❌ Value error in processing: {e}")
        except Exception as e:
            logger.error(f"💥 Unexpected error: {e}", exc_info=True)
        finally:
            logger.info(f"✅ Message for session {payload.get('session_id', 'unknown')} processed and acknowledged")

async def start_worker():
    logger.info("🚀 Initializing DB connection...")
    await init_db()
    logger.info("✅ Database connected.")

    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        async with connection:
            channel = await connection.channel()
            queue = await channel.declare_queue(
                settings.session_queue,
                durable=True,
                arguments={"x-max-priority": 10}
            )
            await channel.set_qos(prefetch_count=1)
            logger.info(f"👷 Worker started on queue '{settings.session_queue}'")
            await queue.consume(process_session)
            await asyncio.Future()  # Keeps worker running
    except asyncio.CancelledError:
        logger.info("🚩 Worker shutting down...")
    except Exception as e:
        logger.error(f"💥 Worker failed to start: {e}", exc_info=True)
    finally:
        await connection.close()
        logger.info("🔌 RabbitMQ connection closed")

if __name__ == "__main__":
    asyncio.run(start_worker())