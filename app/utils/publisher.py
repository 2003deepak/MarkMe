import aio_pika
import json
from app.core.rabbitmq_config import settings

async def send_to_queue(
    queue_name: str,
    payload: dict,
    priority: int = 0,
    delay_ms: int = 0
):
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()

        # choose exchange based on delay
        if delay_ms > 0:
            exchange = await channel.get_exchange("delayed_exchange")
            headers = {"x-delay": delay_ms}
            exchange_type = "DELAYED"
        else:
            exchange = await channel.get_exchange("normal_exchange")
            headers = {}
            exchange_type = "NORMAL"

        message = aio_pika.Message(
            body=json.dumps(payload).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            priority=priority,
            headers=headers
        )

        print("\n=========== RABBITMQ PUBLISH ===========")
        print("TYPE       :", exchange_type)
        print("QUEUE      :", queue_name)
        print("JOB ID     :", payload.get("job_id"))
        print("DELAY MS   :", delay_ms)
        print("HEADERS    :", headers)
        print("=======================================\n")

        await exchange.publish(message, routing_key=queue_name)