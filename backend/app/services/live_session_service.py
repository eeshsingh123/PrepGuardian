import secrets

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis

from app.constants import RedisConstants
from app.interview.tracks import InterviewType


class LiveSessionTicket(BaseModel):
    user_id: str
    session_id: str
    interview_type: InterviewType
    duration_minutes: int


class LiveSessionService:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    def active_session_key(self, user_id: str) -> str:
        return f"{RedisConstants.ACTIVE_SESSION_PREFIX}:{user_id}"

    def ws_ticket_key(self, ticket: str) -> str:
        return f"{RedisConstants.WS_TICKET_PREFIX}:{ticket}"

    async def start_session(self, user_id: str, session_id: str) -> bool:
        return bool(
            await self.redis.set(
                self.active_session_key(user_id),
                session_id,
                ex=RedisConstants.ACTIVE_SESSION_TTL_SECONDS,
                nx=True,
            )
        )

    async def refresh_session(self, user_id: str, session_id: str) -> None:
        key = self.active_session_key(user_id)
        if await self.redis.get(key) == session_id:
            await self.redis.expire(
                key,
                RedisConstants.ACTIVE_SESSION_TTL_SECONDS,
            )

    async def remove_session(self, user_id: str, session_id: str) -> None:
        key = self.active_session_key(user_id)
        if await self.redis.get(key) == session_id:
            await self.redis.delete(key)

    async def issue_session_ticket(self, session: LiveSessionTicket) -> str:
        ticket = secrets.token_urlsafe(32)
        await self.redis.set(
            self.ws_ticket_key(ticket),
            session.model_dump_json(),
            ex=RedisConstants.WS_TICKET_TTL_SECONDS,
        )
        return ticket

    async def consume_session_ticket(self, ticket: str) -> LiveSessionTicket | None:
        raw_ticket = await self.redis.getdel(self.ws_ticket_key(ticket))
        if raw_ticket is None:
            return None
        try:
            return LiveSessionTicket.model_validate_json(raw_ticket)
        except ValidationError:
            return None
