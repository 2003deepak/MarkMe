import asyncio
import aio_pika
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.schemas.timetable import TimetableRepository, Session
from app.core.database import get_db, init_db
from app.core.rabbitmq_config import settings
from bson import ObjectId

async def process_session(message: aio_pika.IncomingMessage):
    print("⚙️ process_session triggered")

    async with message.process():
        try:
            payload = json.loads(message.body.decode())
            print(f"📥 Received session: {payload}")

            timetable_id = payload.get("timetable_id")
            day = payload.get("day")
            slot_index = payload.get("slot_index")
            session_data = payload.get("session", {})
            date = payload.get("date")
            start_time_timestamp = payload.get("start_time_timestamp")

            if not all([timetable_id, day, slot_index is not None, session_data, date, start_time_timestamp]):
                print("❌ Invalid payload missing required fields.")
                return

            # ✅ Transform flat session_data into expected shape
            try:
                session_data["subject"] = ObjectId(session_data["subject"])
                session_data["component"] = session_data.pop("component_type")
                session = Session(**session_data)
            except Exception as e:
                print(f"❌ Invalid session data: {e}")
                return

            db = get_db()
            repo = TimetableRepository(db.client, db.name)

            # ⏱️ Step 1: Only process if start_time is within 15 mins
            session_start = datetime.fromtimestamp(start_time_timestamp, tz=ZoneInfo("Asia/Kolkata"))
            now = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
            if (session_start - now) > timedelta(minutes=15):
                print(f"⏳ Skipping session: start_time more than 15 minutes away ({session_start})")
                return

            # 📌 Step 2: Check for exception
            exception = await db["exception_session"].find_one({
                "timetable_id": timetable_id,
                "date": date,
                "slot_index": slot_index
            })

            if exception:
                action = exception.get("action")
                print(f"⚠️ Exception found: {action}")

                # Step 3: Cancelled
                if action == "cancelled":
                    print(f"🚫 Session cancelled for timetable {timetable_id}, slot {slot_index}")
                    return

                # Step 4: Rescheduled
                elif action == "rescheduled":
                    new_session_data = exception.get("new_session")
                    if not new_session_data:
                        print("⚠️ Rescheduled session missing new_session data.")
                        return

                    try:
                        new_session = Session(**new_session_data)
                        await repo.validate_references(new_session)
                        new_start = datetime.strptime(
                            f"{date} {new_session.start_time}", "%Y-%m-%d %H:%M"
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
                        print(f"🔁 Rescheduled session re-queued for {new_session.start_time}")
                        return
                    except Exception as e:
                        print(f"❌ Reschedule error: {e}")
                        return

                # Step 5: Add (do nothing)
                elif action == "add":
                    pass

            # ✅ Step 6: No exception — store in attendance table
            try:
                await repo.validate_references(session)
                attendance_record = {
                    "timetable_id": ObjectId(timetable_id),
                    "date": datetime.strptime(date, "%Y-%m-%d"),
                    "day": day,
                    "slot_index": slot_index,
                    "subject": session.subject,
                    "component_type": session.component,
                    "students": "",
                }

                await db["attendance"].insert_one(attendance_record)
                print(f"✅ Stored attendance for timetable {timetable_id}, slot {slot_index}")
            except Exception as e:
                print(f"❌ Failed to store attendance: {e}")

        except Exception as e:
            print(f"💥 Unexpected error: {e}")


async def start_worker():
    await init_db()

    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()

    queue = await channel.declare_queue(
        settings.session_queue,
        durable=True,
        arguments={"x-max-priority": 10}
    )

    await channel.set_qos(prefetch_count=1)

    print(f"👷 Worker started on queue '{settings.session_queue}'")
    await queue.consume(process_session)

    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        print("🚩 Worker shutting down...")
        await connection.close()


if __name__ == "__main__":
    asyncio.run(start_worker())
    print("✅ Session Worker started successfully.")
