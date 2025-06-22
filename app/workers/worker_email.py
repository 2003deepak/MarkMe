import asyncio
import aio_pika
import json
from app.core.rabbitmq_config import settings
from app.utils.send_email import send_email


async def email_worker():
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    
    queue = await channel.declare_queue(
        settings.email_queue,
        durable=True,
        arguments={"x-max-priority": 10}  
    )

    print(f"[email_worker] Listening on queue: {settings.email_queue}")

    async with queue.iterator() as messages:
        async for message in messages:
            async with message.process():
                try:
                    payload = json.loads(message.body)
                    data = payload.get("data", {})

                    subject = data.get("subject")
                    email_to = data.get("to")
                    body = data.get("body")

                    if subject and email_to and body:
                        await send_email(subject=subject, email_to=email_to, body=body)
                        print(f"[email_worker] Email sent to: {email_to}")
                    else:
                        print(f"[email_worker] Invalid payload: {payload}")

                except Exception as e:
                    print(f"[email_worker] Error: {str(e)}")


if __name__ == "__main__":
    asyncio.run(email_worker())
