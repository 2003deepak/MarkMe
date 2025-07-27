import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.schemas.timetable import Timetable
from app.core.database import init_db, close_db
from app.utils.publisher import send_to_queue
from app.core.config import settings
from zoneinfo import ZoneInfo
from beanie.odm.fields import Link
from app.schemas.timetable import Timetable as TimetableModel
from bson import ObjectId

async def generate_sessions_for_tomorrow():
    print("🔄 Starting generation of sessions for tomorrow...")

    # Determine the target date
    if settings.ENVIRONMENT == "production":
        tomorrow = datetime.now(tz=ZoneInfo("Asia/Kolkata")) + timedelta(days=1)
    else:
        tomorrow = datetime.now(tz=ZoneInfo("Asia/Kolkata"))

    tomorrow_date = tomorrow.date()
    weekday = tomorrow.strftime("%A")
    print(f"🗕 Target Date: {tomorrow_date} ({weekday})")

    # Fetch timetables using Beanie
    timetables = await TimetableModel.find().to_list()
    print(f"📄 Total timetables fetched: {len(timetables)}")

    final_sessions = []

    for timetable in timetables:
        try:
            # Convert Beanie model to Pydantic schema
            timetable_model = Timetable(**timetable.model_dump())
        except ValueError as e:
            print(f"⚠️ Invalid timetable data for ID {timetable.id}: {str(e)}")
            continue

        timetable_id = str(timetable.id)
        print(f"🗂 Processing timetable: {timetable_id}")

        # Filter valid sessions for the target weekday
        valid_sessions = [
            (idx, session) for idx, session in enumerate(timetable_model.schedule.get(weekday, []))
            if session.start_time and session.end_time and session.subject and session.component
        ]
        print(f"✅ Valid sessions found: {len(valid_sessions)}")

        for idx, session in valid_sessions:
            try:
                # Parse start time for scheduling
                start_time = datetime.strptime(
                    f"{tomorrow_date} {session.start_time}", "%Y-%m-%d %H:%M"
                ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            except ValueError as e:
                print(f"❌ Invalid time format in timetable {timetable_id}, slot {idx}: {str(e)}")
                continue

            # Handle both Link and direct ObjectId cases for subject
            subject_id = None
            if isinstance(session.subject, Link):
                subject_id = str(session.subject.ref.id)  # Get the referenced ObjectId
            elif isinstance(session.subject, ObjectId):
                subject_id = str(session.subject)
            elif isinstance(session.subject, str):
                try:
                    # Validate it's a proper ObjectId string
                    subject_id = str(ObjectId(session.subject))
                except:
                    print(f"❌ Invalid subject ID format: {session.subject}")
                    continue
            else:
                print(f"❌ Unsupported subject reference type: {type(session.subject)}")
                continue

            # Prepare session payload with proper subject ID serialization
            session_payload = {
                "timetable_id": timetable_id,
                "day": weekday,
                "slot_index": idx,
                "session": {
                    "start_time": session.start_time,
                    "end_time": session.end_time,
                    "subject": subject_id,
                    "component_type": session.component
                },
                "date": tomorrow.strftime("%Y-%m-%d"),
                "start_time_timestamp": start_time.timestamp()
            }

            print(f"📦 Prepared session payload: {session_payload}")
            final_sessions.append((start_time, session_payload))

    # Sort sessions by start time
    final_sessions.sort(key=lambda x: x[0])
    print(f"📊 Total sessions to push to queue: {len(final_sessions)}")

    now = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
    queue_name = "session_queue"

    for i, (start_time, session_payload) in enumerate(final_sessions):
        try:
            if settings.ENVIRONMENT == "development":
                # Simulate start_time for development mode
                now = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
                fake_start = now + timedelta(seconds=115 + i * 20)
                fake_end = fake_start + timedelta(hours=1)
                session_payload["session"]["start_time"] = fake_start.strftime("%H:%M")
                session_payload["session"]["end_time"] = fake_end.strftime("%H:%M")
                session_payload["start_time_timestamp"] = fake_start.timestamp()
                delay_ms = 100_00 + i * 20_00  # Simulate 10s, 12s, ...
            else:
                # Calculate delay for production mode (15 minutes before session)
                now = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
                delay_seconds = (start_time - timedelta(minutes=15) - now).total_seconds()
                delay_ms = max(0, int(delay_seconds * 1000))

            # Send to worker queue
            await send_to_queue(queue_name, session_payload, delay_ms=delay_ms)
            print(f"📤 Pushed session {session_payload['timetable_id']}:{session_payload['slot_index']} with delay {delay_ms // 1000} seconds")
        except Exception as e:
            print(f"🚫 Failed to push session {session_payload['timetable_id']}:{session_payload['slot_index']} to queue: {str(e)}")

async def main():
    print("🚀 Initializing DB connection...")
    await init_db()
    print("✅ Database connected.")

    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    if settings.ENVIRONMENT == "production":
        print("🏭 Running in production mode. Scheduling job at 00:05 IST")
        scheduler.add_job(generate_sessions_for_tomorrow, "cron", hour=0, minute=5)
        scheduler.start()
    else:
        print("🧪 Running in development mode. Executing session generation now...")
        await generate_sessions_for_tomorrow()

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Shutting down scheduler...")
        scheduler.shutdown()
        await close_db()
        print("✅ Scheduler and DB closed.")

if __name__ == "__main__":
    asyncio.run(main())