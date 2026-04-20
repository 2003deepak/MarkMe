#redis
import redis.asyncio as redis
from app.core.config import Settings
import logging

settings = Settings()
logger = logging.getLogger("redis")


class RedisManager:
    def __init__(self):
        self._client: redis.Redis | None = None

    async def connect(self):
        if self._client is None:
            self._client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=0,
                decode_responses=True,
                max_connections=100,
                socket_timeout=5,
                socket_connect_timeout=5,
                health_check_interval=30
            )

        try:
            await self._client.ping()
            logger.info(f"✅ Redis connected → {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        except Exception as e:
            logger.error(f"❌ Redis connection failed → {e}")
            raise e

    async def get(self) -> redis.Redis:
        if self._client is None:
            await self.connect()
        return self._client

    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None


# singleton manager (SAFE)
redis_manager = RedisManager()


# dependency/helper
async def get_redis_client() -> redis.Redis:
    return await redis_manager.get()