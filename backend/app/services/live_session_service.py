import secrets

from redis.asyncio import Redis

from app.constants import RedisConstants


class LiveSessionService:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    def session_key(self, user_id: str, session_id: str) -> str:
        return f"{RedisConstants.ACTIVE_SESSION_PREFIX}:{user_id}:{session_id}"

    def ws_ticket_key(self, ticket: str) -> str:
        return f"{RedisConstants.WS_TICKET_PREFIX}:{ticket}"

    async def issue_ws_ticket(self, user_id: str) -> str:
        """
        Creates a single-use ticket for opening a live interview socket.

        Args:
            user_id: Authenticated user the ticket is bound to.
        """
        ticket = secrets.token_urlsafe(32)
        await self.redis.set(
            self.ws_ticket_key(ticket),
            user_id,
            ex=RedisConstants.WS_TICKET_TTL_SECONDS,
        )
        return ticket

    async def consume_ws_ticket(self, ticket: str) -> str | None:
        """
        Atomically consumes a WebSocket ticket and returns its user id.

        Args:
            ticket: One-time ticket from the REST endpoint.
        """
        return await self.redis.getdel(self.ws_ticket_key(ticket))

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
