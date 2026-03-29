import asyncio
import aio_pika
import json
from app.core.rabbitmq_config import settings
from app.utils.imagekit_uploader import delete_file

async def connect_rabbitmq():
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            print("[cleanup_worker] Connected to RabbitMQ")
            return connection
        except Exception as e:
            print(f"[cleanup_worker] RabbitMQ not ready, retrying... {e}")
            await asyncio.sleep(5)


async def cleanup_worker():

    connection = await connect_rabbitmq()
    channel = await connection.channel()

    queue = await channel.declare_queue(
        settings.cleanup_queue,
        durable=True,
        arguments={"x-max-priority": 10}
    )

    print(f"[cleanup_worker] Listening on {settings.cleanup_queue}")

    async with queue.iterator() as messages:
        async for message in messages:
            async with message.process():
                try:
                    payload = json.loads(message.body)

                    if payload.get("type") == "delete_file":
                        file_id = payload.get("data", {}).get("file_id")

                        if file_id:
                            await delete_file(file_id)
                            print(f"[cleanup_worker] Deleted: {file_id}")
                        else:
                            print("[cleanup_worker] Missing file_id")

                    else:
                        print("[cleanup_worker] Unknown message type")

                except Exception as e:
                    print(f"[cleanup_worker] Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(cleanup_worker())