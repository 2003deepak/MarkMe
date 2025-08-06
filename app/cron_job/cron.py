import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.database import init_db, close_db
from app.utils.publisher import send_to_queue
from app.core.config import settings
from app.schemas.session import Session  # Your updated flat session model
from zoneinfo import ZoneInfo
from bson import DBRef

async def generate_sessions_for_tomorrow():
    print("🔄 Starting session scheduler for tomorrow...")

    # Set tomorrow’s date and weekday
    tomorrow = datetime.now(tz=ZoneInfo("Asia/Kolkata")) + timedelta(days=1)
    tomorrow_date = tomorrow.date()
    weekday = tomorrow.strftime("%A")
    print(f"📆 Target: {tomorrow_date} ({weekday})")

    # Fetch sessions for that weekday
    sessions = await Session.find(Session.day == weekday).to_list()
    print(f"📄 Sessions found for {weekday}: {len(sessions)}")

    final_sessions = []

    for session in sessions:
        try:
            start_time = datetime.strptime(
                f"{tomorrow_date} {session.start_time}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

            subject_id = None
            if isinstance(session.subject, DBRef):
                subject_id = str(session.subject.id)
            elif isinstance(session.subject, str):
                subject_id = session.subject

            session_payload = {
                "session_id": str(session.id),
                "date": str(tomorrow_date),
                "day": weekday,
                "start_time_timestamp": start_time.timestamp(),
                "subject": subject_id,
                "program": session.program,
                "department": session.department,
                "semester": session.semester,
                "academic_year": session.academic_year
            }

            final_sessions.append((start_time, session_payload))
        except Exception as e:
            print(f"❌ Failed to prepare session {session.id}: {e}")

    final_sessions.sort(key=lambda x: x[0])

    now = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
    queue_name = "session_queue"

    for i, (start_time, payload) in enumerate(final_sessions):
        try:
            if settings.ENVIRONMENT == "development":
                fake_start = now + timedelta(seconds=100 + i * 20)
                payload["start_time_timestamp"] = fake_start.timestamp()
                delay_ms = 10_000 + i * 2000
            else:
                delay_seconds = (start_time - timedelta(minutes=15) - now).total_seconds()
                delay_ms = max(0, int(delay_seconds * 1000))

            await send_to_queue(queue_name, payload, delay_ms=delay_ms)
            print(f"📤 Scheduled session {payload['session_id']} with delay {delay_ms // 1000}s")
        except Exception as e:
            print(f"🚫 Failed to schedule session {payload['session_id']}: {e}")

async def main():
    print("🚀 Connecting to DB...")
    await init_db()
    print("✅ Connected.")

    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    if settings.ENVIRONMENT == "production":
        scheduler.add_job(generate_sessions_for_tomorrow, "cron", hour=0, minute=5)
        scheduler.start()
    else:
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
