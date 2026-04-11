import asyncio
import aio_pika
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bson import ObjectId
import logging
from datetime import date as dt_date

from app.schemas.session import Session
from app.schemas.subject import Subject
from app.schemas.attendance import Attendance
from app.schemas.exception_session import ExceptionSession
from app.schemas.swap_approval import SwapApproval
from app.core.rabbitmq_config import settings
from app.core.config import settings as app_settings
from app.core.database import init_db
from app.core.redis import get_redis_client

IST = ZoneInfo("Asia/Kolkata")
REDIS_SESSION_JOB_PREFIX = "attendance:job:"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("session_worker")

async def connect_rabbitmq():
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            print("[session_worker] Connected to RabbitMQ")
            return connection
        except Exception as e:
            print(f"[session_worker] RabbitMQ not ready, retrying... {e}")
            await asyncio.sleep(5)

# redis
async def get_job_id_from_redis(redis, session_id: str, date_str: str):
    key = f"{REDIS_SESSION_JOB_PREFIX}{session_id}:{date_str}"
    return await redis.get(key)


# worker
async def process_session(message: aio_pika.IncomingMessage):

    redis = await get_redis_client()
    async with message.process():
        try:
            payload = json.loads(message.body.decode())
            logger.info(f"📥 Payload received → {payload}")

            session_id = payload.get("session_id")
            date_str = payload.get("date")
            job_id = payload.get("job_id")
            is_exception = payload.get("is_exception", False)
            exception_id = payload.get("exception_id")
            start_ts = payload.get("start_time_timestamp")
            
            
            now = datetime.now(tz=IST)
            start_time = datetime.fromtimestamp(start_ts, tz=IST)
            
            print("\n============== WORKER DEBUG ==============")
            print("SESSION:", session_id)
            print("JOB ID (payload):", job_id)
            print("NOW:", now)
            print("START TIME:", start_time)
            print("TIME DIFF (min):", (start_time - now).total_seconds() / 60)

            if not session_id or not date_str or not job_id or not start_ts:
                logger.error("❌ Invalid payload")
                return

            redis_job_id = await get_job_id_from_redis(session_id, date_str)
            
            print("REDIS JOB ID:", redis_job_id)
            print("PAYLOAD JOB ID:", job_id)

            if redis_job_id:
                print("REDIS == PAYLOAD ?", redis_job_id.decode() == job_id)
            else:
                print("REDIS KEY MISSING")

            print("=========================================\n")

            if redis_job_id != job_id:
                logger.info("🚫 Stale or cancelled job")
                return

            if start_time < now:
                logger.info("⏰ Session already passed")
                await redis.delete(f"{REDIS_SESSION_JOB_PREFIX}{session_id}:{date_str}")
                return

            if app_settings.ENVIRONMENT == "production":
                if (start_time - now) > timedelta(minutes=15):
                    logger.info("⏳ Not within execution window")
                    return

            exception = None
            swap = None

            # exception handling
            if is_exception:
                exception = await ExceptionSession.get(
                    ObjectId(exception_id),
                    fetch_links=True
                )
                if not exception:
                    logger.error("❌ Exception not found")
                    return

                action = exception.action.upper()
                logger.info(f"⚠️ Exception action → {action}")

                if action == "CANCEL":
                    await redis.delete(f"{REDIS_SESSION_JOB_PREFIX}{session_id}:{date_str}")
                    logger.info("🚫 Cancelled session")
                    return

                if exception.swap_id:
                    swap = await SwapApproval.get(
                        exception.swap_id.id,
                        fetch_links=True
                    )
                    if not swap or swap.status != "APPROVED":
                        logger.info("⏸️ Swap pending → skipping execution")
                        return

            # subject
            subject_id = payload.get("subject")
            subject = None
            if subject_id:
                subject = await Subject.get(ObjectId(subject_id))

            # attendance creation
            attendance_data = dict(
                date=dt_date.fromisoformat(date_str),
                day=payload.get("day"),
                subject=ObjectId(subject_id) if subject_id else None,
                program=payload.get("program"),
                department=payload.get("department"),
                semester=payload.get("semester"),
                academic_year=payload.get("academic_year"),
                students=""
            )

            if exception:
                attendance = Attendance(
                    exception_session=exception.id,
                    **attendance_data
                )
            else:
                attendance = Attendance(
                    session=session_id,
                    **attendance_data
                )

            await attendance.insert()
            logger.info("✅ Attendance created")

            await redis.delete(f"{REDIS_SESSION_JOB_PREFIX}{session_id}:{date_str}")

        except Exception as e:
            logger.error("💥 Worker error", exc_info=True)


async def start_worker():
    await init_db()

    connection = await connect_rabbitmq()
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)

        queue = await channel.declare_queue(
            settings.session_queue,
            durable=True,
            arguments={"x-max-priority": 10}
        )

        logger.info("👷 Session worker running")
        await queue.consume(process_session)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(start_worker())