import unittest

from app.constants import RedisConstants
from app.services.live_session_service import LiveSessionService


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
    async def test_register_rejects_duplicate_session_until_cleanup(self):
        redis = FakeRedis()
        service = LiveSessionService(redis)

        first = await service.register_session("pg_user", "sess_1")
        second = await service.register_session("pg_user", "sess_1")

        self.assertTrue(first)
        self.assertFalse(second)

    async def test_refresh_and_remove_session_touch_expected_key(self):
        redis = FakeRedis()
        service = LiveSessionService(redis)
        await service.register_session("pg_user", "sess_1")

        await service.refresh_session("pg_user", "sess_1")
        await service.remove_session("pg_user", "sess_1")

        expected_key = service.session_key("pg_user", "sess_1")
        self.assertEqual(redis.expired[0][0], expected_key)
        self.assertEqual(redis.deleted[0], expected_key)


class WsTicketTests(unittest.IsolatedAsyncioTestCase):
    async def test_ticket_is_single_use_and_bound_to_its_user(self):
        redis = FakeRedis()
        service = LiveSessionService(redis)

        ticket = await service.issue_ws_ticket("user_a")

        self.assertGreaterEqual(len(ticket), 32)
        self.assertEqual(await service.consume_ws_ticket(ticket), "user_a")
        self.assertIsNone(await service.consume_ws_ticket(ticket))

    async def test_ticket_expires_after_configured_ttl(self):
        redis = FakeRedis()
        service = LiveSessionService(redis)

        ticket = await service.issue_ws_ticket("user_a")
        redis.advance(RedisConstants.WS_TICKET_TTL_SECONDS + 1)

        self.assertIsNone(await service.consume_ws_ticket(ticket))

    async def test_tickets_return_only_their_issuing_user(self):
        redis = FakeRedis()
        service = LiveSessionService(redis)

        ticket_a = await service.issue_ws_ticket("user_a")
        ticket_b = await service.issue_ws_ticket("user_b")

        self.assertEqual(await service.consume_ws_ticket(ticket_a), "user_a")
        self.assertEqual(await service.consume_ws_ticket(ticket_b), "user_b")
        self.assertIsNone(await service.consume_ws_ticket("not-a-ticket"))

    async def test_ticket_uses_expected_redis_key_and_ttl(self):
        redis = FakeRedis()
        service = LiveSessionService(redis)

        ticket = await service.issue_ws_ticket("user_a")

        stored = redis.values[service.ws_ticket_key(ticket)]
        self.assertEqual(
            service.ws_ticket_key(ticket),
            f"{RedisConstants.WS_TICKET_PREFIX}:{ticket}",
        )
        self.assertEqual(stored["value"], "user_a")
        self.assertEqual(stored["ttl"], RedisConstants.WS_TICKET_TTL_SECONDS)
