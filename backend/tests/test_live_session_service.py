import json
import unittest

from app.constants import RedisConstants
from app.interview.tracks import InterviewType
from app.services.live_session_service import LiveSessionService, LiveSessionTicket


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expired = []
        self.deleted = []
        self.now = 0.0

    def advance(self, seconds: float):
        self.now += seconds

    def is_expired(self, item: dict) -> bool:
        expires_at = item["expires_at"]
        return expires_at is not None and self.now >= expires_at

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values and not self.is_expired(self.values[key]):
            return False
        self.values[key] = {
            "value": value,
            "ttl": ex,
            "expires_at": self.now + ex if ex is not None else None,
        }
        return True

    async def get(self, key):
        item = self.values.get(key)
        if item is None or self.is_expired(item):
            return None
        return item["value"]

    async def expire(self, key, ttl):
        self.expired.append((key, ttl))
        if key in self.values:
            self.values[key]["ttl"] = ttl
            self.values[key]["expires_at"] = self.now + ttl
        return True

    async def delete(self, key):
        self.deleted.append(key)
        self.values.pop(key, None)
        return 1

    async def getdel(self, key):
        item = self.values.get(key)
        if item is None:
            return None
        del self.values[key]
        if self.is_expired(item):
            return None
        return item["value"]


class LiveSessionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_session_rejects_a_second_active_session(self):
        redis = FakeRedis()
        service = LiveSessionService(redis)

        first = await service.start_session("pg_user", "sess_1")
        second = await service.start_session("pg_user", "sess_2")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(
            await redis.get(service.active_session_key("pg_user")),
            "sess_1",
        )

    async def test_expired_active_session_allows_a_new_session(self):
        redis = FakeRedis()
        service = LiveSessionService(redis)
        await service.start_session("pg_user", "sess_1")

        redis.advance(RedisConstants.ACTIVE_SESSION_TTL_SECONDS + 1)

        self.assertTrue(await service.start_session("pg_user", "sess_2"))

    async def test_refresh_and_remove_only_touch_the_matching_session(self):
        redis = FakeRedis()
        service = LiveSessionService(redis)
        await service.start_session("pg_user", "sess_1")

        await service.refresh_session("pg_user", "other_session")
        await service.remove_session("pg_user", "other_session")
        self.assertEqual(
            await redis.get(service.active_session_key("pg_user")),
            "sess_1",
        )

        redis.advance(80)
        await service.refresh_session("pg_user", "sess_1")
        redis.advance(20)
        self.assertEqual(
            await redis.get(service.active_session_key("pg_user")),
            "sess_1",
        )

        await service.remove_session("pg_user", "sess_1")
        self.assertIsNone(
            await redis.get(service.active_session_key("pg_user"))
        )


class WsTicketTests(unittest.IsolatedAsyncioTestCase):
    def build_ticket(self, user_id: str = "pg_user") -> LiveSessionTicket:
        return LiveSessionTicket(
            user_id=user_id,
            session_id="sess_server",
            interview_type=InterviewType.LLD,
            duration_minutes=45,
        )

    async def test_ticket_is_single_use_and_bound_to_its_user(self):
        redis = FakeRedis()
        service = LiveSessionService(redis)

        ticket = await service.issue_session_ticket(self.build_ticket("user_a"))

        self.assertGreaterEqual(len(ticket), 32)
        self.assertEqual(
            await service.consume_session_ticket(ticket),
            self.build_ticket("user_a"),
        )
        self.assertIsNone(await service.consume_session_ticket(ticket))

    async def test_ticket_expires_after_configured_ttl(self):
        redis = FakeRedis()
        service = LiveSessionService(redis)

        ticket = await service.issue_session_ticket(self.build_ticket())
        redis.advance(RedisConstants.WS_TICKET_TTL_SECONDS + 1)

        self.assertIsNone(await service.consume_session_ticket(ticket))

    async def test_tickets_return_only_their_issuing_user(self):
        redis = FakeRedis()
        service = LiveSessionService(redis)

        ticket_a = await service.issue_session_ticket(self.build_ticket("user_a"))
        ticket_b = await service.issue_session_ticket(self.build_ticket("user_b"))

        self.assertEqual(
            (await service.consume_session_ticket(ticket_a)).user_id,
            "user_a",
        )
        self.assertEqual(
            (await service.consume_session_ticket(ticket_b)).user_id,
            "user_b",
        )
        self.assertIsNone(await service.consume_session_ticket("not-a-ticket"))

    async def test_ticket_payload_uses_expected_redis_key_and_ttl(self):
        redis = FakeRedis()
        service = LiveSessionService(redis)

        ticket = await service.issue_session_ticket(self.build_ticket())
        key = service.ws_ticket_key(ticket)
        stored = redis.values[key]

        self.assertEqual(
            key,
            f"{RedisConstants.WS_TICKET_PREFIX}:{ticket}",
        )
        self.assertEqual(
            json.loads(stored["value"]),
            {
                "user_id": "pg_user",
                "session_id": "sess_server",
                "interview_type": "lld",
                "duration_minutes": 45,
            },
        )
        self.assertEqual(stored["ttl"], RedisConstants.WS_TICKET_TTL_SECONDS)
