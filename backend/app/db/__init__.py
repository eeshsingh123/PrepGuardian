from app.db.mongo import connect_mongo, close_mongo
from app.db.redis import close_redis, connect_redis
from app.db.sqlite import connect_sqlite, close_sqlite
from app.logger import logger


async def init_databases(app=None):
    """
    Initializes all database connections. Called once during FastAPI
    startup via the lifespan context manager.
    """
    await connect_mongo()
    await connect_sqlite()
    if app is not None:
        await connect_redis(app)
    logger.info("All databases initialized.")


async def close_databases(app=None):
    """
    Gracefully closes all database connections. Called once during
    FastAPI shutdown via the lifespan context manager.
    """
    if app is not None:
        await close_redis(app)
    await close_mongo()
    await close_sqlite()
    logger.info("All database connections closed.")
