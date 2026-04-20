from typing import Annotated

from fastapi import Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.db.redis import get_redis


def get_database(request: Request) -> AsyncIOMotorDatabase:
    db = getattr(request.app.state, "mongo_db", None)
    if db is None:
        raise RuntimeError("MongoDB is not initialized.")
    return db


DatabaseDep = Annotated[AsyncIOMotorDatabase, Depends(get_database)]
RedisDep = Annotated[Redis, Depends(get_redis)]
