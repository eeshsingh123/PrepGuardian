from fastapi import FastAPI, Request
from redis.asyncio import Redis

from app.config import settings
from app.logger import logger


async def connect_redis(app: FastAPI) -> None:
    client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    await client.ping()
    app.state.redis = client
    logger.info("Redis connected.")


async def close_redis(app: FastAPI) -> None:
    client: Redis | None = getattr(app.state, "redis", None)
    if client is not None:
        await client.aclose()
        app.state.redis = None
        logger.info("Redis connection closed.")


def get_redis(request: Request) -> Redis:
    client: Redis | None = getattr(request.app.state, "redis", None)
    if client is None:
        raise RuntimeError("Redis is not initialized.")
    return client
