from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.logger import logger


_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_mongo():
    global _client, _db
    _client = AsyncIOMotorClient(settings.MONGO_URI)
    _db = _client[settings.MONGO_DB_NAME]

    # Verify the connection is alive before proceeding
    await _client.admin.command("ping")
    logger.info(f"MongoDB connected to '{settings.MONGO_DB_NAME}'.")

    await _create_indexes()


async def _create_indexes():
    """
    Creates indexes on collections for efficient querying.
    - users.user_id: unique lookup by backend-generated ID
    - users.username: unique lookup for login
    - refresh_tokens.token_hash: unique lookup for refresh rotation
    - refresh_tokens.expires_at: TTL cleanup for expired refresh tokens
    - conversations.session_id: unique lookup for fetching a single transcript
    - conversations.(user_id, started_at desc): compound index for listing
      a user's conversations sorted newest-first
    """
    users = _db["users"]
    await users.create_index("user_id", unique=True)
    await users.create_index("username", unique=True)

    refresh_tokens = _db["refresh_tokens"]
    await refresh_tokens.create_index("token_hash", unique=True)
    await refresh_tokens.create_index([("user_id", 1), ("expires_at", -1)])
    await refresh_tokens.create_index("expires_at", expireAfterSeconds=0)

    conversations = _db["conversations"]
    await conversations.create_index("session_id", unique=True)
    await conversations.create_index(
        [("user_id", 1), ("started_at", -1)],
        name="user_conversations_by_recency",
    )
    logger.info("MongoDB indexes ensured.")


async def close_mongo():
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB connection closed.")


def get_mongo_db() -> AsyncIOMotorDatabase:
    """
    Returns the MongoDB database instance. Must be called after connect_mongo()
    has been awaited during application startup.

    Raises:
        RuntimeError: If called before the database has been initialized.
    """
    if _db is None:
        raise RuntimeError("MongoDB is not initialized. Call connect_mongo() first.")
    return _db
