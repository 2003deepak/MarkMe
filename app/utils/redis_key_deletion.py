from redis.asyncio import Redis
from app.core.redis import get_redis_client
import asyncio
import logging

logger = logging.getLogger("app.utils.redis_invalidator")

async def invalidate_redis_keys(match: str):
   
    cursor = 0
    total_deleted = 0
    
    redis = await get_redis_client()

    logger.info(f"🧹 Starting Redis invalidation for pattern: {match}")

    while True:
        cursor, keys = await redis.scan(cursor=cursor, match=match, count=100)

        if keys:
            deleted = await redis.delete(*keys)
            total_deleted += deleted
            logger.debug(f"Deleted {deleted} keys: {keys}")

        if cursor == 0:
            break

    logger.info(f"✅ Redis invalidation done. Total deleted keys: {total_deleted}")
    return total_deleted
