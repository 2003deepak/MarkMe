import asyncio
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bson import DBRef

from app.core.database import init_db, close_db
from app.core.redis import redis_client
from app.utils.publisher import send_to_queue
from app.core.config import settings
from app.schemas.session import Session
from app.schemas.exception_session import ExceptionSession


REDIS_SESSION_JOB_PREFIX = "attendance:job:"  # Redis key prefix for session-job mapping
SESSION_QUEUE_NAME = "session_queue"


async def store_job_id_in_redis(session_id: str, date_str: str, job_id: str, expiration_seconds: int):
   
    key = f"{REDIS_SESSION_JOB_PREFIX}{session_id}:{date_str}"
    await redis_client.set(key, job_id, ex=expiration_seconds)


async def get_job_id_from_redis(session_id: str, date_str: str):
    
    key = f"{REDIS_SESSION_JOB_PREFIX}{session_id}:{date_str}"
    job_id = await redis_client.get(key, encoding="utf-8")
    return job_id


async def delete_job_id_from_redis(session_id: str, date_str: str):
    
    key = f"{REDIS_SESSION_JOB_PREFIX}{session_id}:{date_str}"
    await redis_client.delete(key)


async def generate_sessions_for_tomorrow():

    print("🔄 Starting session scheduler for tomorrow...")

    tomorrow = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
    tomorrow_date = tomorrow.date()
    date_str = str(tomorrow_date)
    # weekday = tomorrow.strftime("%A")  # ✅ Fixed weekday calc
    weekday = "Friday"
    print(f"📆 Target date: {date_str} ({weekday})")

    sessions = await Session.find(Session.day == weekday, fetch_links=True).to_list()
    print(f"📄 Sessions found for {weekday}: {len(sessions)}")

    final_sessions = []

    for session in sessions:
        try:
            session_id = str(session.id)

            # Check for exception for tomorrow
            exception = await ExceptionSession.find_one(
                ExceptionSession.session == session.id,
                ExceptionSession.date == tomorrow_date
            )

            if exception:
                action = exception.action.lower()
                print(f"⚠️ Exception found for session {session_id}: {action}")

                if action == "cancel":
                    print(f"🚫 Skipping cancelled session {session_id}")
                    await delete_job_id_from_redis(session_id, date_str)
                    continue

                elif action == "rescheduled" and exception.new_slot:
                    # Use rescheduled start time
                    start_time_str = exception.new_slot.start_time
                    start_time = datetime.strptime(f"{date_str} {start_time_str}", "%Y-%m-%d %H:%M")
                    start_time = start_time.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
                else:
                    # No valid reschedule data, skip scheduling
                    continue
            else:
                # Use original session time
                start_time = datetime.strptime(f"{date_str} {session.start_time}", "%Y-%m-%d %H:%M")
                start_time = start_time.replace(tzinfo=ZoneInfo("Asia/Kolkata"))

            # Generate unique job ID per session for tomorrow
            job_id = str(uuid.uuid4())

            # Store job ID in Redis with 2-day expiry (48 hours)
            expiration_seconds = 2 * 24 * 3600
            await store_job_id_in_redis(session_id, date_str, job_id, expiration_seconds)

            subject_id = None
            if isinstance(session.subject, DBRef):
                subject_id = str(session.subject.id)
            elif isinstance(session.subject, str):
                subject_id = session.subject
            elif hasattr(session.subject, "id"):
                subject_id = str(session.subject.id)
            else:
                print(f"❌ Invalid subject format for session {session_id}")
                continue

            # ✅ Add exception_id + is_exception flag
            session_payload = {
                "session_id": session_id,
                "date": date_str,
                "day": weekday,
                "start_time_timestamp": start_time.timestamp(),
                "subject": subject_id,
                "program": session.program,
                "department": session.department,
                "semester": session.semester,
                "academic_year": session.academic_year,
                "job_id": job_id,
            }

            if exception:
                session_payload["exception_id"] = str(exception.id)
                session_payload["is_exception"] = True
            else:
                session_payload["is_exception"] = False

            final_sessions.append((start_time, session_payload))
        except Exception as e:
            print(f"❌ Error preparing session {session.id}: {e}")

    # Sort by start time
    final_sessions.sort(key=lambda x: x[0])

    now = datetime.now(tz=ZoneInfo("Asia/Kolkata"))

    for i, (start_time, payload) in enumerate(final_sessions):
        try:
            delay_seconds = (start_time - timedelta(minutes=15) - now).total_seconds()
            delay_ms = delay_seconds * 1000

            if settings.ENVIRONMENT == "development":
                # For dev/testing: fake scheduling times
                fake_start = now + timedelta(seconds=100 + i * 20)
                payload["start_time_timestamp"] = fake_start.timestamp()
                delay_ms = 10_000 + i * 2000

            await send_to_queue(SESSION_QUEUE_NAME, payload, delay_ms=delay_ms)
            print(f"📤 Scheduled session {payload['session_id']} with delay {delay_ms // 1000}s")
        except Exception as e:
            print(f"🚫 Failed to schedule session {payload['session_id']}: {e}")


async def main():
    print("🚀 Connecting to DB and Redis...")
    await init_db()

    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    if settings.ENVIRONMENT == "production":
        # Schedule cron job daily at 00:05 IST
        scheduler.add_job(generate_sessions_for_tomorrow, "cron", hour="00", minute="16")
        scheduler.start()
    else:
        # For development/testing run immediately once
        await generate_sessions_for_tomorrow()

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Shutting down...")
        scheduler.shutdown()
        await close_db()
        print("✅ Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
