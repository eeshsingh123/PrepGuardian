import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import bcrypt
from fastapi import HTTPException, Response

from app.schemas import UserCreate
from app.services.auth_service import AuthService, TokenService, user_from_doc


class FakeInsertResult:
    inserted_id = "fake"


class FakeUpdateResult:
    modified_count = 1


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def insert_one(self, doc):
        self.docs.append(doc.copy())
        return FakeInsertResult()

    async def find_one(self, query):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return doc.copy()
        return None

    async def update_one(self, query, update):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                return FakeUpdateResult()
        return FakeUpdateResult()


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, ttl, value):
        self.values[key] = value
        return True


class AuthServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = SimpleNamespace(
            users=FakeCollection(),
            refresh_tokens=FakeCollection(),
        )
        self.redis = FakeRedis()
        self.service = AuthService(self.db, self.redis)

    async def test_signup_creates_user_and_refresh_session(self):
        response = Response()

        session = await self.service.signup(
            UserCreate(username="  Alice  ", password="correct horse battery"),
            response,
        )

        self.assertEqual(session.user.username, "alice")
        self.assertEqual(session.token_type, "bearer")
        self.assertTrue(session.access_token)
        self.assertEqual(len(self.db.refresh_tokens.docs), 1)
        self.assertNotIn("correct horse battery", self.db.users.docs[0]["password_hash"])

    async def test_login_rejects_invalid_password(self):
        response = Response()
        await self.service.signup(
            UserCreate(username="alice", password="correct horse battery"),
            response,
        )

        with self.assertRaises(HTTPException) as ctx:
            await self.service.login("alice", "wrong", Response())

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.headers["WWW-Authenticate"], "Bearer")

    async def test_legacy_bcrypt_login_rehashes_password(self):
        password = "correct horse battery"
        bcrypt_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        self.db.users.docs.append(
            {
                "user_id": "pg_legacy",
                "username": "legacy",
                "password_hash": bcrypt_hash,
                "name": None,
                "experience": None,
                "target_company": None,
                "target_level": None,
                "preferences": None,
                "is_onboarded": False,
                "created_at": datetime.now(UTC).replace(tzinfo=None),
                "updated_at": datetime.now(UTC).replace(tzinfo=None),
            }
        )

        await self.service.login("legacy", password, Response())

        self.assertNotEqual(self.db.users.docs[0]["password_hash"], bcrypt_hash)

    async def test_refresh_rotates_refresh_token(self):
        response = Response()
        await self.service.signup(
            UserCreate(username="alice", password="correct horse battery"),
            response,
        )
        refresh_token = response.headers["set-cookie"].split("pg_refresh_token=")[1].split(";")[0]

        refreshed = await self.service.refresh(refresh_token, Response())

        self.assertTrue(refreshed.access_token)
        self.assertIsNotNone(self.db.refresh_tokens.docs[0]["revoked_at"])
        self.assertEqual(len(self.db.refresh_tokens.docs), 2)

    async def test_revoked_refresh_token_is_rejected(self):
        response = Response()
        await self.service.signup(
            UserCreate(username="alice", password="correct horse battery"),
            response,
        )
        refresh_token = response.headers["set-cookie"].split("pg_refresh_token=")[1].split(";")[0]
        await self.service.refresh(refresh_token, Response())

        with self.assertRaises(HTTPException) as ctx:
            await self.service.refresh(refresh_token, Response())

        self.assertEqual(ctx.exception.status_code, 401)

    async def test_decode_access_token_uses_user_id_subject(self):
        response = Response()
        session = await self.service.signup(
            UserCreate(username="alice", password="correct horse battery"),
            response,
        )

        payload = TokenService().decode_access_token(session.access_token)

        self.assertEqual(payload.sub, session.user.user_id)


class UserDocumentTests(unittest.TestCase):
    def test_user_from_doc_removes_mongo_id(self):
        user = user_from_doc(
            {
                "_id": "mongo-id",
                "user_id": "pg_user",
                "username": "alice",
                "password_hash": "hash",
                "created_at": datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
            }
        )

        self.assertEqual(user.user_id, "pg_user")
