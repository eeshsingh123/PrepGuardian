from typing import Annotated

from fastapi import Depends, Header, WebSocketException, status
from fastapi.security import OAuth2PasswordBearer
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.constants import RedisConstants
from app.dependencies import DatabaseDep, RedisDep
from app.schemas import UserPublic
from app.services.auth_service import TokenService, invalid_credentials_exception, user_from_doc


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


async def resolve_user_from_access_token(
    token: str,
    db: AsyncIOMotorDatabase,
    redis: Redis | None = None,
) -> UserPublic:
    payload = TokenService().decode_access_token(token)
    if redis is not None:
        revoked = await redis.get(
            f"{RedisConstants.REVOKED_ACCESS_TOKEN_PREFIX}:{payload.jti}"
        )
        if revoked:
            raise invalid_credentials_exception()
    user_doc = await db.users.find_one({"user_id": payload.sub})
    if not user_doc:
        raise invalid_credentials_exception()
    return UserPublic.model_validate(user_from_doc(user_doc))


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DatabaseDep,
    redis: RedisDep,
) -> UserPublic:
    return await resolve_user_from_access_token(token, db, redis)


async def get_optional_authorization_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


async def get_websocket_user(
    token: str | None,
    db: AsyncIOMotorDatabase,
    redis: Redis,
) -> UserPublic:
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    try:
        return await resolve_user_from_access_token(token, db, redis)
    except Exception as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION) from exc
