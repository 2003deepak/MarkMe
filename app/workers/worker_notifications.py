import asyncio
import aio_pika
import json
import firebase_admin
from firebase_admin import credentials, messaging
from app.core.rabbitmq_config import settings

# ------------------- Firebase Init -------------------
cred = credentials.Certificate(
    "app\google-services.json"
)
firebase_admin.initialize_app(cred)

CHUNK_SIZE = 500


# ------------------- Main FCM Sender -------------------
async def send_fcm_to_tokens(payload: dict):
    tokens = payload.get("tokens", [])
    title = payload.get("title", "")
    body = payload.get("body", "")
    custom_data = payload.get("data", {})

    if not tokens:
        print("[FCM] No tokens provided")
        return

    total = len(tokens)
    print(f"[FCM] Sending notifications to {total} tokens...")

    for i in range(0, total, CHUNK_SIZE):
        chunk = tokens[i:i + CHUNK_SIZE]

        # Build the multicast message
        message = messaging.MulticastMessage(
            tokens=chunk,
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=custom_data,
        )

        # USE THE ASYNC FUNCTION THAT EXISTS IN YOUR SDK
        response = await messaging.send_each_for_multicast_async(message)

        print(
            f"[FCM] Batch {i // CHUNK_SIZE + 1}: "
            f"{response.success_count}/{len(chunk)} delivered"
        )

        # Handle failed tokens
        if response.failure_count > 0:
            for idx, resp in enumerate(response.responses):
                if not resp.success:
                    print(f"[FCM] Failed token: {chunk[idx]} — {resp.exception}")


# ------------------- Worker Listener -------------------
async def notification_worker():
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()

    queue = await channel.declare_queue(
        settings.notification_queue,
        durable=True,
        arguments={"x-max-priority": 10}
    )

    print(f"[Worker] Listening on queue: {settings.notification_queue}")

    async with queue.iterator() as messages:
        async for message in messages:
            async with message.process():
                try:
                    payload = json.loads(message.body)
                    print("[Worker] Received message:", payload)
                    await send_fcm_to_tokens(payload)
                except Exception as e:
                    print(f"[Worker] Error: {str(e)}")


# ------------------- Entry Point -------------------
if __name__ == "__main__":
    asyncio.run(notification_worker())
