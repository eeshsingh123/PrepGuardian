from pydantic import BaseModel, Field

from app.schemas.users import UserPublic, UsernamePasswordBase


class LoginRequest(UsernamePasswordBase):
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthSession(TokenResponse):
    user: UserPublic


class TokenPayload(BaseModel):
    sub: str
    jti: str
    token_type: str
    exp: int
    iss: str


class RefreshTokenRecord(BaseModel):
    token_hash: str
    user_id: str
    expires_at: int
    revoked_at: int | None = None
