import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import HTTPException, Response, status
from jwt.exceptions import InvalidTokenError
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError
from pwdlib import PasswordHash
from pymongo.errors import DuplicateKeyError
from redis.asyncio import Redis

from app.config import Settings, settings
from app.constants import AuthConstants, RedisConstants
from app.schemas import AuthSession, TokenPayload, UserCreate, UserInDB, UserPublic


class PasswordService:
    def __init__(self) -> None:
        self.password_hash = PasswordHash.recommended()
        self.dummy_hash = self.password_hash.hash("dummy-password")

    def hash_password(self, password: str) -> str:
        return self.password_hash.hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            if password_hash.startswith("$2a$") or password_hash.startswith("$2b$"):
                return bcrypt.checkpw(password.encode(), password_hash.encode())
            return self.password_hash.verify(password, password_hash)
        except Exception:
            return False

    def should_rehash(self, password_hash: str) -> bool:
        return password_hash.startswith("$2a$") or password_hash.startswith("$2b$")


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TokenService:
    def __init__(self, app_settings: Settings = settings) -> None:
        self.settings = app_settings

    def create_access_token(self, user: UserPublic) -> tuple[str, int, str, datetime]:
        issued_at = datetime.now(UTC)
        expires_at = issued_at + timedelta(
            minutes=AuthConstants.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        jti = uuid.uuid4().hex
        payload = {
            "sub": user.user_id,
            "jti": jti,
            "token_type": AuthConstants.ACCESS_TOKEN_TYPE,
            "iat": issued_at,
            "exp": expires_at,
            "iss": AuthConstants.JWT_ISSUER,
        }
        token = jwt.encode(
            payload,
            self.settings.JWT_SECRET_KEY,
            algorithm=AuthConstants.JWT_ALGORITHM,
        )
        return token, AuthConstants.ACCESS_TOKEN_EXPIRE_MINUTES * 60, jti, expires_at

    def decode_access_token(self, token: str) -> TokenPayload:
        try:
            payload = jwt.decode(
                token,
                self.settings.JWT_SECRET_KEY,
                algorithms=[AuthConstants.JWT_ALGORITHM],
                issuer=AuthConstants.JWT_ISSUER,
            )
            token_payload = TokenPayload.model_validate(payload)
        except (InvalidTokenError, ValidationError) as exc:
            raise invalid_credentials_exception() from exc
        if token_payload.token_type != AuthConstants.ACCESS_TOKEN_TYPE:
            raise invalid_credentials_exception()
        return token_payload

    def create_refresh_token(self) -> tuple[str, str, datetime]:
        token = secrets.token_urlsafe(64)
        expires_at = utc_now() + timedelta(
            days=AuthConstants.REFRESH_TOKEN_EXPIRE_DAYS
        )
        return token, self.hash_token(token), expires_at

    def hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()


def invalid_credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def user_from_doc(user_doc: dict) -> UserInDB:
    return UserInDB(**{k: v for k, v in user_doc.items() if k != "_id"})


class AuthService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        redis: Redis | None = None,
        token_service: TokenService | None = None,
        password_service: PasswordService | None = None,
    ) -> None:
        self.db = db
        self.redis = redis
        self.token_service = token_service or TokenService()
        self.password_service = password_service or PasswordService()

    async def signup(self, request: UserCreate, response: Response) -> AuthSession:
        now = utc_now()
        user_doc = {
            "user_id": f"pg_{uuid.uuid4().hex[:12]}",
            "username": request.username,
            "password_hash": self.password_service.hash_password(request.password),
            "name": None,
            "experience": None,
            "target_company": None,
            "target_level": None,
            "preferences": None,
            "is_onboarded": False,
            "created_at": now,
            "updated_at": now,
        }
        try:
            await self.db.users.insert_one(user_doc)
        except DuplicateKeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already taken.",
            ) from exc
        user = user_from_doc(user_doc)
        return await self.create_session(user, response)

    async def login(
        self, username: str, password: str, response: Response
    ) -> AuthSession:
        user_doc = await self.db.users.find_one({"username": username})
        if not user_doc:
            self.password_service.verify_password(password, self.password_service.dummy_hash)
            raise invalid_credentials_exception()

        user = user_from_doc(user_doc)
        if not self.password_service.verify_password(password, user.password_hash):
            raise invalid_credentials_exception()

        if self.password_service.should_rehash(user.password_hash):
            await self.db.users.update_one(
                {"user_id": user.user_id},
                {
                    "$set": {
                        "password_hash": self.password_service.hash_password(password),
                        "updated_at": utc_now(),
                    }
                },
            )
        return await self.create_session(user, response)

    async def create_session(
        self, user: UserPublic, response: Response
    ) -> AuthSession:
        access_token, expires_in, _, _ = self.token_service.create_access_token(user)
        refresh_token, token_hash, expires_at = self.token_service.create_refresh_token()
        await self.db.refresh_tokens.insert_one(
            {
                "token_hash": token_hash,
                "user_id": user.user_id,
                "created_at": utc_now(),
                "expires_at": expires_at,
                "revoked_at": None,
            }
        )
        set_refresh_cookie(response, refresh_token)
        return AuthSession(
            user=UserPublic.model_validate(user),
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
        )

    async def refresh(self, refresh_token: str | None, response: Response) -> AuthSession:
        if not refresh_token:
            raise invalid_credentials_exception()
        token_hash = self.token_service.hash_token(refresh_token)
        token_doc = await self.db.refresh_tokens.find_one({"token_hash": token_hash})
        if not token_doc:
            raise invalid_credentials_exception()
        if token_doc.get("revoked_at") is not None:
            raise invalid_credentials_exception()
        if token_doc["expires_at"] <= utc_now():
            raise invalid_credentials_exception()

        await self.db.refresh_tokens.update_one(
            {"token_hash": token_hash},
            {"$set": {"revoked_at": utc_now()}},
        )
        user_doc = await self.db.users.find_one({"user_id": token_doc["user_id"]})
        if not user_doc:
            raise invalid_credentials_exception()
        return await self.create_session(user_from_doc(user_doc), response)

    async def logout(
        self, refresh_token: str | None, access_token: str | None, response: Response
    ) -> dict[str, bool]:
        if refresh_token:
            await self.db.refresh_tokens.update_one(
                {"token_hash": self.token_service.hash_token(refresh_token)},
                {"$set": {"revoked_at": utc_now()}},
            )
        if access_token and self.redis:
            try:
                payload = self.token_service.decode_access_token(access_token)
                ttl = max(payload.exp - int(datetime.now(UTC).timestamp()), 0)
                if ttl:
                    await self.redis.setex(
                        f"{RedisConstants.REVOKED_ACCESS_TOKEN_PREFIX}:{payload.jti}",
                        ttl,
                        "1",
                    )
            except HTTPException:
                pass
        clear_refresh_cookie(response)
        return {"ok": True}


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AuthConstants.REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        domain=settings.AUTH_COOKIE_DOMAIN,
        path=AuthConstants.REFRESH_COOKIE_PATH,
        max_age=AuthConstants.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AuthConstants.REFRESH_COOKIE_NAME,
        domain=settings.AUTH_COOKIE_DOMAIN,
        path=AuthConstants.REFRESH_COOKIE_PATH,
    )
