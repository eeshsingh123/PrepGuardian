from redis.asyncio import Redis

from app.constants import RedisConstants


class LiveSessionService:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    def session_key(self, user_id: str, session_id: str) -> str:
        return f"{RedisConstants.ACTIVE_SESSION_PREFIX}:{user_id}:{session_id}"

    async def register_session(self, user_id: str, session_id: str) -> bool:
        return bool(
            await self.redis.set(
                self.session_key(user_id, session_id),
                "active",
                ex=RedisConstants.ACTIVE_SESSION_TTL_SECONDS,
                nx=True,
            )
        )

    async def refresh_session(self, user_id: str, session_id: str) -> None:
        await self.redis.expire(
            self.session_key(user_id, session_id),
            RedisConstants.ACTIVE_SESSION_TTL_SECONDS,
        )

    async def remove_session(self, user_id: str, session_id: str) -> None:
        await self.redis.delete(self.session_key(user_id, session_id))
