import asyncio
import aio_pika
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bson import ObjectId
import logging

from app.schemas.session import Session
from app.schemas.subject import Subject
from app.schemas.attendance import Attendance
from app.schemas.exception_session import ExceptionSession
from app.core.rabbitmq_config import settings
from app.core.database import init_db
from app.core.redis import redis_client  # Assuming redis_client is an async Redis instance

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REDIS_SESSION_JOB_PREFIX = "attendance:job:"


async def get_job_id_from_redis(session_id: str, date_str: str):
    key = f"{REDIS_SESSION_JOB_PREFIX}{session_id}:{date_str}"
    job_id = await redis_client.get(key)
    return job_id


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
                "subject",
                "job_id"
            ]

            if not all(payload.get(field) is not None for field in required_fields):
                logger.error(f"❌ Invalid payload: Missing required fields: {required_fields}")
                return

            session_id = payload["session_id"]
            date = payload["date"]
            start_time_timestamp = payload["start_time_timestamp"]
            subject_id = payload["subject"]
            message_job_id = payload["job_id"]

            # Validate IDs
            try:
                session_obj_id = ObjectId(session_id)
                subject_id_obj = ObjectId(subject_id)
            except Exception as e:
                logger.error(f"❌ Invalid ObjectId format for session_id or subject_id: {e}")
                return

            date_str = date  # Assuming ISO format 'YYYY-MM-DD'

            # Fetch job_id from Redis and check if this message is still valid
            redis_job_id = await get_job_id_from_redis(session_id, date_str)
            if redis_job_id is None:
                logger.info(f"🚫 Job ID not found in Redis; likely cancelled for session {session_id} on {date}")
                return
            if redis_job_id != message_job_id:
                logger.info(f"🚫 Job ID mismatch for session {session_id}: message job_id {message_job_id} vs Redis {redis_job_id}. Skipping.")
                return

            session_start = datetime.fromtimestamp(start_time_timestamp, tz=ZoneInfo("Asia/Kolkata"))
            now = datetime.now(tz=ZoneInfo("Asia/Kolkata"))

            if (session_start - now) > timedelta(minutes=15):
                logger.info(f"⏳ Skipping session, starts later than 15 min: {session_start}")
                return

            # Fetch Session
            session = await Session.get(session_obj_id)
            if not session:
                logger.error(f"❌ Session not found: {session_id}")
                return

            # Fetch Subject
            subject = await Subject.get(subject_id_obj)
            if not subject:
                logger.error(f"❌ Subject not found: {subject_id}")
                return

            # Check for exceptions on this session + date
            exception = await ExceptionSession.find_one(
                ExceptionSession.session == session_obj_id,
                ExceptionSession.date == datetime.strptime(date, "%Y-%m-%d")
            )
            if exception:
                action = exception.action.lower()
                logger.info(f"⚠️ Exception found: {action}")

                if action == "cancel":
                    logger.info(f"🚫 Cancelled session {session_id} on {date}")
                    # Since cancelled, remove job_id from Redis to prevent future processing
                    await redis_client.delete(f"{REDIS_SESSION_JOB_PREFIX}{session_id}:{date_str}")
                    return

                elif action == "rescheduled":
                    if exception.new_slot:
                        new_start = datetime.strptime(
                            f"{date} {exception.new_slot.start_time}", "%Y-%m-%d %H:%M"
                        ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

                        if new_start < now:
                            logger.info(f"⏰ Rescheduled session {session_id} already passed at {new_start}")
                            # Remove stale job_id from Redis
                            await redis_client.delete(f"{REDIS_SESSION_JOB_PREFIX}{session_id}:{date_str}")
                            return

                        # This situation ideally should never happen here, as new job should be enqueued at reschedule time
                        logger.info(f"🔄 Rescheduled session occurs at {new_start}, skipping old job")
                        return
                    else:
                        logger.error("⚠️ Rescheduled session missing new_slot data")
                        return

            # Store attendance if no cancellation/rescheduling applies
            attendance = Attendance(
                session=session_obj_id,
                date=datetime.strptime(date, "%Y-%m-%d"),
                day=payload.get("day"),
                subject=subject_id_obj,
                program=payload.get("program"),
                department=payload.get("department"),
                semester=payload.get("semester"),
                academic_year=payload.get("academic_year"),
                students=""  # Initial empty, can be updated later
            )
            await attendance.insert()
            logger.info(f"✅ Stored attendance for session {session_id}")

            # After successful processing, delete job id from Redis to prevent accidental reprocessing
            await redis_client.delete(f"{REDIS_SESSION_JOB_PREFIX}{session_id}:{date_str}")

        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to decode payload: {e}")
        except Exception as e:
            logger.error(f"💥 Unexpected error: {e}", exc_info=True)


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
            await asyncio.Future()
    except asyncio.CancelledError:
        logger.info("🚩 Worker shutting down...")
    except Exception as e:
        logger.error(f"💥 Worker failed to start: {e}", exc_info=True)
    finally:
        await connection.close()
        logger.info("🔌 RabbitMQ connection closed")


if __name__ == "__main__":
    asyncio.run(start_worker())
