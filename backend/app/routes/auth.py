from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response
from fastapi.security import OAuth2PasswordRequestForm

from app.constants import AuthConstants
from app.dependencies import DatabaseDep, RedisDep
from app.schemas import AuthSession, LoginRequest, UserCreate, UserPublic
from app.security import get_current_user, get_optional_authorization_token
from app.services.auth_service import AuthService


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/signup", response_model=AuthSession, status_code=201)
async def signup(
    request: UserCreate,
    response: Response,
    db: DatabaseDep,
    redis: RedisDep,
) -> AuthSession:
    return await AuthService(db, redis).signup(request, response)


@router.post("/login", response_model=AuthSession)
async def login(
    request: LoginRequest,
    response: Response,
    db: DatabaseDep,
    redis: RedisDep,
) -> AuthSession:
    return await AuthService(db, redis).login(
        request.username,
        request.password,
        response,
    )


@router.post("/token", response_model=AuthSession)
async def oauth_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    response: Response,
    db: DatabaseDep,
    redis: RedisDep,
) -> AuthSession:
    return await AuthService(db, redis).login(
        form_data.username.strip().lower(),
        form_data.password,
        response,
    )


@router.post("/refresh", response_model=AuthSession)
async def refresh(
    response: Response,
    db: DatabaseDep,
    redis: RedisDep,
    refresh_token: Annotated[
        str | None,
        Cookie(alias=AuthConstants.REFRESH_COOKIE_NAME),
    ] = None,
) -> AuthSession:
    return await AuthService(db, redis).refresh(refresh_token, response)


@router.post("/logout")
async def logout(
    response: Response,
    db: DatabaseDep,
    redis: RedisDep,
    refresh_token: Annotated[
        str | None,
        Cookie(alias=AuthConstants.REFRESH_COOKIE_NAME),
    ] = None,
    access_token: Annotated[
        str | None,
        Depends(get_optional_authorization_token),
    ] = None,
) -> dict[str, bool]:
    return await AuthService(db, redis).logout(refresh_token, access_token, response)


@router.get("/me", response_model=UserPublic)
async def me(current_user: Annotated[UserPublic, Depends(get_current_user)]) -> UserPublic:
    return current_user
