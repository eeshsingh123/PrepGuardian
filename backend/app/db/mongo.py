from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.logger import logger


async def connect_mongo(app: FastAPI):
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB_NAME]

    # Verify the connection is alive before proceeding
    await client.admin.command("ping")
    logger.info(f"MongoDB connected to '{settings.MONGO_DB_NAME}'.")

    # Store in app state
    app.state.mongo_client = client
    app.state.mongo_db = db

    await _create_indexes(db)


async def _create_indexes(db: AsyncIOMotorDatabase):
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
    users = db["users"]
    await users.create_index("user_id", unique=True)
    await users.create_index("username", unique=True)

    refresh_tokens = db["refresh_tokens"]
    await refresh_tokens.create_index("token_hash", unique=True)
    await refresh_tokens.create_index([("user_id", 1), ("expires_at", -1)])
    await refresh_tokens.create_index("expires_at", expireAfterSeconds=0)

    conversations = db["conversations"]
    await conversations.create_index("session_id", unique=True)
    await conversations.create_index(
        [("user_id", 1), ("started_at", -1)],
        name="user_conversations_by_recency",
    )
    logger.info("MongoDB indexes ensured.")


async def close_mongo(app: FastAPI):
    client = getattr(app.state, "mongo_client", None)
    if client:
        client.close()
        app.state.mongo_client = None
        app.state.mongo_db = None
        logger.info("MongoDB connection closed.")
