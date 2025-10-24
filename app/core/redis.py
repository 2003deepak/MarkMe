import redis.asyncio as redis
import logging
from app.core.config import Settings

# Initialize Settings
settings = Settings()

# Setup logger
logger = logging.getLogger("redis_client")
logging.basicConfig(level=logging.INFO)

# Create a Redis client (singleton pattern)
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=0,
    decode_responses=True,
    max_connections=100,
    socket_timeout=5,
    socket_connect_timeout=5,
    health_check_interval=30
)

async def get_redis_client():
    """Get the Redis client instance with connection verification."""
    try:
        pong = await redis_client.ping()
        if pong:
            logger.info(f"✅ Redis connected successfully to {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        return redis_client
    except redis.ConnectionError as e:
        logger.error(f"❌ Redis connection failed: {e}. Attempting to reconnect...")
        await redis_client.close()
        new_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            decode_responses=True,
            max_connections=100,
            socket_timeout=10,
            socket_connect_timeout=5,
            health_check_interval=30
        )
        try:
            pong = await new_client.ping()
            if pong:
                logger.info(f"✅ Redis reconnected successfully to {settings.REDIS_HOST}:{settings.REDIS_PORT}")
            return new_client
        except redis.ConnectionError as e2:
            logger.critical(f"❌ Redis reconnection failed: {e2}")
            raise e2
