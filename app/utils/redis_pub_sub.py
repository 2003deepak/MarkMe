import json
from contextlib import asynccontextmanager
from app.core.redis import get_redis_client
import logging
from redis.exceptions import ConnectionError, TimeoutError
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def publish_to_channel(channel_name: str, message: dict):
    retries = 3
    for attempt in range(retries):
        try:
            redis_client = await get_redis_client()
            # Create a copy of the message for logging, omitting or truncating annotated_image
            log_message = message.copy()
            if "annotated_image" in log_message:
                log_message["annotated_image"] = (
                    log_message["annotated_image"][:50] + "..."
                    if len(log_message["annotated_image"]) > 50
                    else log_message["annotated_image"]
                )
            payload = json.dumps(message)
            await redis_client.publish(channel_name, payload)
            # logger.info(f"[publish_to_channel] Published to {channel_name}: {json.dumps(log_message)}")
            break
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"[publish_to_channel] Attempt {attempt + 1} failed: {str(e)}")
            if attempt == retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff

@asynccontextmanager
async def subscribe_to_channel(channel_name: str):
    retries = 3
    pubsub = None
    redis_client = None
    try:
        # Retry loop to establish subscription
        for attempt in range(retries):
            try:
                redis_client = await get_redis_client()
                pubsub = redis_client.pubsub()
                await pubsub.subscribe(channel_name)
                logger.info(f"[subscribe_to_channel] Subscribed to {channel_name}")
                break
            except (ConnectionError, TimeoutError) as e:
                logger.error(f"[subscribe_to_channel] Attempt {attempt + 1} failed: {str(e)}")
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

        # Yield the pubsub object for use in the async with block
        yield pubsub
    finally:
        # Cleanup: Unsubscribe and close the pubsub connection
        if pubsub:
            try:
                await pubsub.unsubscribe(channel_name)
                await pubsub.close()
                logger.info(f"[subscribe_to_channel] Unsubscribed from {channel_name}")
            except Exception as e:
                logger.error(f"[subscribe_to_channel] Error during cleanup: {str(e)}")
        if redis_client:
            try:
                await redis_client.close()
                logger.info(f"[subscribe_to_channel] Redis client closed")
            except Exception as e:
                logger.error(f"[subscribe_to_channel] Error closing Redis client: {str(e)}")