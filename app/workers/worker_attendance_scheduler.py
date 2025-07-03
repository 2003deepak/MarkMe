import asyncio
import aio_pika
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.schemas.timetable import TimetableRepository, Session
from app.core.database import get_db
from app.core.rabbitmq_config import settings

async def process_session(message: aio_pika.IncomingMessage):
    async with message.process():
        try:
            # Decode and parse the message
            payload = json.loads(message.body.decode())
            print(f"Received session: {payload}")

            # Extract session data
            timetable_id = payload.get("timetable_id")
            day = payload.get("day")
            slot_index = payload.get("slot_index")
            session_data = payload.get("session", {})
            date = payload.get("date")
            start_time_timestamp = payload.get("start_time_timestamp")

            if not all([timetable_id, day, slot_index is not None, session_data, date, start_time_timestamp]):
                print(f"Invalid payload missing required fields: {payload}")
                return

            # Validate session using Pydantic model
            try:
                session = Session(**session_data)
            except ValueError as e:
                print(f"Invalid session data for timetable {timetable_id}, slot {slot_index}: {str(e)}")
                return

            # Initialize database and repository
            db = get_db() 
            repo = TimetableRepository(db.client, db.name)

            # Validate subject reference
            try:
                await repo.validate_references(session)
            except ValueError as e:
                print(f"Validation failed for session in timetable {timetable_id}, slot {slot_index}: {str(e)}")
                return

            # Calculate session start time
            try:
                session_start = datetime.fromtimestamp(start_time_timestamp, tz=ZoneInfo("Asia/Kolkata"))
            except ValueError as e:
                print(f"Invalid start time timestamp for timetable {timetable_id}, slot {slot_index}: {str(e)}")
                return

            # Check if current time is within 5 minutes before session start
            current_time = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
            time_window_start = session_start - timedelta(minutes=5)
            if not (time_window_start <= current_time < session_start):
                print(f"Session for timetable {timetable_id}, slot {slot_index} not in 5-minute window (current: {current_time}, start: {session_start})")
                return  # Discard (acknowledge) the session without requeuing

            # Check for exceptions in the exceptions collection
            exception = await db["exceptions"].find_one({
                "timetable_id": timetable_id,
                "date": date,
                "slot_index": slot_index
            })

            if exception:
                action = exception.get("action")
                print(f"Exception found for timetable {timetable_id}, slot {slot_index}: action={action}")

                if action == "cancelled":
                    print(f"Session cancelled for timetable {timetable_id}, slot {slot_index}")
                    return

                elif action == "rescheduled":
                    new_session_data = exception.get("new_session")
                    if not new_session_data:
                        print(f"No new session data for rescheduled session in timetable {timetable_id}, slot {slot_index}")
                        return

                    # Validate new session data
                    try:
                        new_session = Session(**new_session_data)
                        await repo.validate_references(new_session)
                    except ValueError as e:
                        print(f"Invalid rescheduled session data for timetable {timetable_id}, slot {slot_index}: {str(e)}")
                        return

                    # Calculate new start time
                    try:
                        new_start_time = datetime.strptime(
                            f"{date} {new_session.start_time}", "%Y-%m-%d %H:%M"
                        ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
                    except ValueError as e:
                        print(f"Invalid time format for rescheduled session: {str(e)}")
                        return

                    # Queue the rescheduled session
                    new_payload = {
                        **payload,
                        "session": new_session_data,
                        "start_time_timestamp": new_start_time.timestamp()
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
                    print(f"Queued rescheduled session for timetable {timetable_id}, slot {slot_index}")
                    return

                elif action == "add":
                    new_session_data = exception.get("new_session")
                    if not new_session_data:
                        print(f"No new session data for added session in timetable {timetable_id}, slot {slot_index}")
                        return

                    # Validate new session data
                    try:
                        new_session = Session(**new_session_data)
                        await repo.validate_references(new_session)
                    except ValueError as e:
                        print(f"Invalid added session data for timetable {timetable_id}, slot {slot_index}: {str(e)}")
                        return

                    # Calculate new start time
                    try:
                        new_start_time = datetime.strptime(
                            f"{date} {new_session.start_time}", "%Y-%m-%d %H:%M"
                        ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
                    except ValueError as e:
                        print(f"Invalid time format for added session: {str(e)}")
                        return

                    # Queue the new session
                    new_payload = {
                        "timetable_id": timetable_id,
                        "day": day,
                        "slot_index": slot_index,
                        "session": new_session_data,
                        "date": date,
                        "start_time_timestamp": new_start_time.timestamp()
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
                    print(f"Queued added session for timetable {timetable_id}, slot {slot_index}")
                    return

            # No exception: store session in attendance collection
            attendance_record = {
                "timetable_id": timetable_id,
                "day": day,
                "slot_index": slot_index,
                "session": session_data,
                "date": date,
                "start_time_timestamp": start_time_timestamp,
                "created_at": current_time.isoformat()
            }
            await db["attendance"].insert_one(attendance_record)
            print(f"Stored session in attendance DB for timetable {timetable_id}, slot {slot_index}")

            print(f"Completed processing session for timetable {timetable_id}, slot {slot_index}")

        except Exception as e:
            print(f"Error processing message: {str(e)}")
            # Message is auto-acknowledged via message.process()

async def start_worker():
    # Connect to RabbitMQ
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()

    # Declare the queue (priority not needed, but queue must exist)
    queue = await channel.declare_queue(
        settings.session_queue,
        durable=True
    )

    # Set prefetch count to process one message at a time
    await channel.set_qos(prefetch_count=1)

    # Start consuming messages
    print(f"Worker started, waiting for messages in {settings.session_queue}")
    await queue.consume(process_session)

    # Keep the worker running
    try:
        await asyncio.Future()  # Run forever until cancelled
    except asyncio.CancelledError:
        print("Shutting down worker")
        await connection.close()
        print("Worker stopped")

if __name__ == "__main__":
    asyncio.run(start_worker())