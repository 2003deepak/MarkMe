import aio_pika
import json
from app.core.rabbitmq_config import settings

async def send_to_queue(queue_name: str, payload: dict, priority: int = 0, delay_ms: int = 0):
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()

        # 🧠 Delayed exchange must already be declared in rabbitmq_setup.py
        exchange = await channel.get_exchange("delayed_exchange")

        # Prepare headers
        headers = {}
        if delay_ms > 0:
            headers["x-delay"] = delay_ms

        message = aio_pika.Message(
            body=json.dumps(payload).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            priority=priority,
            headers=headers
        )

        # ✅ Publish to delayed exchange using queue name as routing key
        await exchange.publish(message, routing_key=queue_name)
