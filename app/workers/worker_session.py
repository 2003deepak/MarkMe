import asyncio
import aio_pika
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bson import ObjectId
from pymongo.errors import PyMongoError

from app.schemas.timetable import Timetable, Session
from app.schemas.subject import Subject
from app.schemas.attendance import Attendance
from app.schemas.exception_session import ExceptionSession
from app.core.rabbitmq_config import settings
from app.core.database import init_db


async def process_session(message: aio_pika.IncomingMessage):
    print("⚙️ process_session triggered")

    async with message.process():
        try:
            payload = json.loads(message.body.decode())
            print(f"📥 Received session payload:\n{json.dumps(payload, indent=2)}")

            # Validate required fields
            required_fields = [
                "timetable_id", 
                "day", 
                "slot_index", 
                "session", 
                "date", 
                "start_time_timestamp"
            ]
            
            if not all(payload.get(field) is not None for field in required_fields):
                print("❌ Invalid payload: Missing required fields.")
                return

            timetable_id = payload["timetable_id"]
            day = payload["day"]
            slot_index = payload["slot_index"]
            session_data = payload["session"]
            date = payload["date"]
            start_time_timestamp = payload["start_time_timestamp"]

            # Validate ObjectId format for timetable_id and subject
            try:
                timetable_id_obj = ObjectId(timetable_id)
                subject_id_obj = ObjectId(session_data["subject"])
            except Exception as e:
                print(f"❌ Invalid ID format: {e}")
                return

            # 🎯 Fetch linked Subject using direct ObjectId
            subject = await Subject.get(subject_id_obj)
            if not subject:
                print(f"❌ Subject not found: {session_data['subject']}")
                return

            # Prepare session data with proper types
            session_data["subject"] = subject
            session_data["component"] = session_data.pop("component_type")
            session = Session(**session_data)

            # ⏳ Check if session is within 15 mins
            session_start = datetime.fromtimestamp(start_time_timestamp, tz=ZoneInfo("Asia/Kolkata"))
            now = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
            
            if (session_start - now) > timedelta(minutes=15):
                print(f"⏳ Skipping session, starts later than 15 min: {session_start}")
                return

            # 🔁 Check for ExceptionSession
            try:
                exception = await ExceptionSession.find_one(
                    ExceptionSession.timetable_id == timetable_id_obj,
                    ExceptionSession.date == datetime.strptime(date, "%Y-%m-%d"),
                    ExceptionSession.slot_reference.slot_index == slot_index
                )
            except PyMongoError as e:
                print(f"❌ DB error during ExceptionSession lookup: {e}")
                return

            if exception:
                action = exception.action.lower()
                print(f"⚠️ Exception found: {action}")

                if action == "cancelled":
                    print(f"🚫 Cancelled session for timetable {timetable_id}, slot {slot_index}")
                    return

                elif action == "rescheduled":
                    new_session_data = exception.new_slot.model_dump() if exception.new_slot else None
                    if not new_session_data:
                        print("⚠️ Rescheduled session missing new data")
                        return

                    new_start = datetime.strptime(
                        f"{date} {new_session_data['start_time']}", "%Y-%m-%d %H:%M"
                    ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

                    new_payload = {
                        **payload,
                        "session": new_session_data,
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
                    print(f"🔁 Rescheduled session re-queued for {new_start}")
                    return

                elif action == "add":
                    print("📌 Exception 'add' — continuing to mark attendance.")

            # 🗓️ Fetch linked Timetable using direct ObjectId
            timetable = await Timetable.get(timetable_id_obj)
            if not timetable:
                print(f"❌ Timetable not found: {timetable_id}")
                return

            # ✅ Store Attendance with direct ObjectId references
            try:
                attendance = Attendance(
                    timetable_id=timetable_id_obj,  # Direct ObjectId
                    date=datetime.strptime(date, "%Y-%m-%d"),
                    day=day,
                    slot_index=slot_index,
                    subject=subject_id_obj,  # Direct ObjectId
                    component_type=session.component,
                    students=""
                )
                
                await attendance.insert()
                print(f"✅ Stored attendance for timetable {timetable_id}, slot {slot_index}")
                print(f"📝 Attendance document: {attendance.model_dump_json(indent=2)}")

            except (ValueError, PyMongoError) as e:
                print(f"❌ Failed to store attendance: {e}")

        except json.JSONDecodeError as e:
            print(f"❌ Failed to decode payload: {e}")
        except Exception as e:
            print(f"💥 Unexpected error: {e}")
            import traceback
            traceback.print_exc()


async def start_worker():
    print("🚀 Initializing DB connection...")
    await init_db()
    print("✅ Database connected.")

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
            print(f"👷 Worker started on queue '{settings.session_queue}'")
            await queue.consume(process_session)
            await asyncio.Future()  # Keeps worker running
    except asyncio.CancelledError:
        print("🚩 Worker shutting down...")
    except Exception as e:
        print(f"💥 Worker failed to start: {e}")
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(start_worker())