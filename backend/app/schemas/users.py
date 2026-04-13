from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.constants import AuthConstants


class UsernamePasswordBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()


class UserCreate(UsernamePasswordBase):
    password: str = Field(
        ...,
        min_length=AuthConstants.MIN_PASSWORD_LENGTH,
        max_length=128,
    )


class OnboardingRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    experience: str = Field(..., min_length=1, max_length=200)
    target_company: str = Field(..., min_length=1, max_length=100)
    target_level: str = Field(..., min_length=1, max_length=50)
    preferences: str = Field(..., max_length=2000)


class UserPublic(BaseModel):
    user_id: str
    username: str
    name: str | None = None
    experience: str | None = None
    target_company: str | None = None
    target_level: str | None = None
    preferences: str | None = None
    is_onboarded: bool = False
    created_at: datetime
    updated_at: datetime | None = None


class UserInDB(UserPublic):
    password_hash: str
