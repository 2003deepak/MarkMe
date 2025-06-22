import aio_pika
import json
from app.core.rabbitmq_config import settings

async def send_to_queue(queue_name: str, payload: dict, priority: int = 0):
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()

        # Make sure this declaration matches the one from setup
        await channel.declare_queue(
            queue_name,
            durable=True,
            arguments={"x-max-priority": 10}  
        )

        message = aio_pika.Message(
            body=json.dumps(payload).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            priority=priority
        )
        await channel.default_exchange.publish(message, routing_key=queue_name)