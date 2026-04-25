import unittest

from app.services.live_session_service import LiveSessionService


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expired = []
        self.deleted = []

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = {"value": value, "ttl": ex}
        return True

    async def expire(self, key, ttl):
        self.expired.append((key, ttl))
        return True

    async def delete(self, key):
        self.deleted.append(key)
        self.values.pop(key, None)
        return 1


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

