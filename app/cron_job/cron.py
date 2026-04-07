import asyncio
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bson import DBRef

from app.core.database import init_db, close_db
from app.core.redis import get_redis_client
from app.utils.publisher import send_to_queue
from app.core.config import settings
from app.schemas.session import Session
from app.schemas.exception_session import ExceptionSession
from app.schemas.swap_approval import SwapApproval


REDIS_SESSION_JOB_PREFIX = "attendance:job:"
SESSION_QUEUE_NAME = "session_queue"
IST = ZoneInfo("Asia/Kolkata")

redis = None


# redis
async def store_job_id(session_id: str, date_str: str, job_id: str):
    key = f"{REDIS_SESSION_JOB_PREFIX}{session_id}:{date_str}"
    await redis.set(key, job_id, ex=48 * 3600)


async def delete_job_id(session_id: str, date_str: str):
    key = f"{REDIS_SESSION_JOB_PREFIX}{session_id}:{date_str}"
    await redis.delete(key)


# scheduler
async def generate_sessions_for_today():
    print("🔄 Scheduler started")

    now = datetime.now(tz=IST)
    target_date = now.date()
    date_str = str(target_date)
    weekday = now.strftime("%A")

    sessions = await Session.find(Session.day == weekday, Session.is_active == True, fetch_links=True).to_list()
    final_jobs = []

    for session in sessions:
        try:
            session_id = str(session.id)

            exception = await ExceptionSession.find_one(
                ExceptionSession.session == session.id,
                ExceptionSession.date == target_date,
                fetch_links=True
            )

            # default timing
            start_time = datetime.strptime(
                f"{date_str} {session.start_time}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=IST)

            # exception handling
            if exception:
                action = exception.action.upper()

                # CANCEL
                if action == "CANCEL":
                    print(f"🚫 Cancelled {session_id}")
                    await delete_job_id(session_id, date_str)
                    continue

                # RESCHEDULE
                if action == "RESCHEDULE":
                    if exception.swap_id:
                        swap = await SwapApproval.get(
                            exception.swap_id.id, fetch_links=True
                        )

                        if swap.status != "APPROVED":
                            print(f"⏸️ Pending swap {session_id}")
                            continue

                    start_time = datetime.strptime(
                        f"{date_str} {exception.start_time}",
                        "%Y-%m-%d %H:%M"
                    ).replace(tzinfo=IST)

            job_id = str(uuid.uuid4())
            await store_job_id(session_id, date_str, job_id)

            # subject resolution
            if isinstance(session.subject, DBRef):
                subject_id = str(session.subject.id)
            else:
                subject_id = str(session.subject.id)

            payload = {
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
                "is_exception": bool(exception),
                "exception_id": str(exception.id) if exception else None,
            }

            final_jobs.append((start_time, payload))

        except Exception as e:
            print(f"❌ Error {session.id}: {e}")

    # ADD exceptions (extra lectures)
    add_exceptions = await ExceptionSession.find(
        ExceptionSession.action == "Add",
        ExceptionSession.date == target_date,
        fetch_links=True
    ).to_list()

    for ex in add_exceptions:
        if ex.swap_id:
            swap = await SwapApproval.get(ex.swap_id.id)
            if swap.status != "APPROVED":
                continue

        start_time = datetime.strptime(
            f"{date_str} {ex.start_time}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=IST)

        job_id = str(uuid.uuid4())

        payload = {
            "session_id": str(ex.id),
            "date": date_str,
            "day": weekday,
            "start_time_timestamp": start_time.timestamp(),
            "subject": None,
            "program": None,
            "department": ex.created_by.department,
            "semester": None,
            "academic_year": None,
            "job_id": job_id,
            "is_exception": True,
            "exception_id": str(ex.id),
        }

        final_jobs.append((start_time, payload))

    # scheduling
    final_jobs.sort(key=lambda x: x[0])

    for i, (start_time, payload) in enumerate(final_jobs):
        delay = (start_time - timedelta(minutes=15) - now).total_seconds()

        if delay <= 0:
            continue

        if settings.ENVIRONMENT == "development":
            delay = 5 + i * 5

        await send_to_queue(
            SESSION_QUEUE_NAME,
            payload,
            delay_ms=int(delay * 1000)
        )

        print(f"📤 Scheduled {payload['session_id']} in {int(delay)}s")


# runner
async def main():
    await init_db()
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    
    redis = await get_redis_client()

    if settings.ENVIRONMENT == "production":
        scheduler.add_job(generate_sessions_for_today, "cron", hour=0, minute=0)
        scheduler.start()
    else:
        await generate_sessions_for_today()

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
