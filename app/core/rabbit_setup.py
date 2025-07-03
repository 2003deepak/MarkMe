import aio_pika
from app.core.rabbitmq_config import settings

# 🎯 Define max priority levels per queue
QUEUE_PRIORITY_CONFIG = {
    settings.face_queue: 10,        # Highest (face recognition)
    settings.email_queue: 10,        # Medium (5 - Registration email , 10 - Reset Password Mail) , 1
    settings.embedding_queue: 10,     # Lowest (vector embeddings)
    settings.session_queue :10
    
}

async def setup_rabbitmq():
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()

    for queue_name, max_priority in QUEUE_PRIORITY_CONFIG.items():
        await channel.declare_queue(
            queue_name,
            durable=True,
            arguments={"x-max-priority": max_priority}
        )
        print(f"[RabbitMQ] Queue '{queue_name}' declared with max priority {max_priority}")

    await connection.close()
