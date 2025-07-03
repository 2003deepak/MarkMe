import redis.asyncio as redis
from app.core.config import Settings

# Initialize Settings
settings = Settings()

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
        await redis_client.ping()
        return redis_client
    except redis.ConnectionError:
        # Reconnect if connection is lost
        await redis_client.close()
        return redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            decode_responses=True,
            max_connections=100,
            socket_timeout=5,
            socket_connect_timeout=5,
            health_check_interval=30
        )