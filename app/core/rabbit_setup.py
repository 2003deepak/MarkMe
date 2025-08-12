import aio_pika
from app.core.rabbitmq_config import settings

QUEUE_PRIORITY_CONFIG = {
    settings.face_recog_queue: 10,
    settings.email_queue: 10,
    settings.embedding_queue: 10,
    settings.session_queue: 10
}

async def setup_rabbitmq():
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()

    delayed_exchange = await channel.declare_exchange(
        "delayed_exchange",
        type="x-delayed-message",
        durable=True,
        arguments={"x-delayed-type": "direct"}
    )

    for queue_name, max_priority in QUEUE_PRIORITY_CONFIG.items():
        queue = await channel.declare_queue(
            queue_name,
            durable=True,
            arguments={"x-max-priority": max_priority}
        )
        await queue.bind(delayed_exchange, routing_key=queue_name)
        print(f"[RabbitMQ] Queue '{queue_name}' declared & bound to delayed exchange with max priority {max_priority}")

    await connection.close()
