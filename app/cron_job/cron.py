import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.schemas.timetable import Timetable
from app.core.database import get_db
from app.utils.publisher import send_to_queue


async def generate_sessions_for_tomorrow():
    db = get_db()  
    timetables_collection = db["timetables"]

    tomorrow = datetime.now() + timedelta(days=1)
    tomorrow_date = tomorrow.date()
    weekday = tomorrow.strftime("%A")

    timetables = await timetables_collection.find().to_list(None)
    final_sessions = []

    for timetable in timetables:
        try:
            timetable_model = Timetable(**timetable)
        except ValueError as e:
            print(f"Invalid timetable data for ID {timetable.get('_id')}: {str(e)}")
            continue

        timetable_id = str(timetable["_id"])

        valid_sessions = [
            (idx, session) for idx, session in enumerate(timetable_model.schedule.get(weekday, []))
            if session.start_time and session.end_time and session.subject
        ]

        for idx, session in valid_sessions:
            try:
                start_time = datetime.strptime(
                    f"{tomorrow_date} {session.start_time}", "%Y-%m-%d %H:%M"
                )
            except ValueError as e:
                print(f"Invalid time format in timetable {timetable_id}, slot {idx}: {str(e)}")
                continue

            session_payload = {
                "timetable_id": timetable_id,
                "day": weekday,
                "slot_index": idx,
                "session": {
                    "start_time": session.start_time,
                    "end_time": session.end_time,
                    "subject": session.subject,
                },
                "date": tomorrow.strftime("%Y-%m-%d"),
                "start_time_timestamp": start_time.timestamp()
            }
            final_sessions.append(session_payload)

    final_sessions.sort(key=lambda x: x["start_time_timestamp"])

    queue_name = "session_queue"
    for session_payload in final_sessions:
        try:
            await send_to_queue(queue_name, session_payload)
            print(f"Pushed session {session_payload['timetable_id']}:{session_payload['slot_index']} to queue")
        except Exception as e:
            print(f"Failed to push session {session_payload['timetable_id']}:{session_payload['slot_index']} to queue: {str(e)}")


async def main():
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(generate_sessions_for_tomorrow, "cron", hour=0, minute=5)
    scheduler.start()
    print("Scheduler started for midnight session generation")

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down scheduler")
        scheduler.shutdown()
        print("Scheduler stopped")


if __name__ == "__main__":
    asyncio.run(main())
