from typing import Annotated

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.db.mongo import get_mongo_db
from app.db.redis import get_redis


def get_database() -> AsyncIOMotorDatabase:
    return get_mongo_db()


DatabaseDep = Annotated[AsyncIOMotorDatabase, Depends(get_database)]
RedisDep = Annotated[Redis, Depends(get_redis)]
