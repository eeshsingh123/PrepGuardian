from fastapi import APIRouter

from app.models import (
    SignupRequest,
    LoginRequest,
    OnboardingRequest,
    UserResponse,
)
from app.services.user_service import (
    signup_user,
    login_user,
    update_onboarding,
    get_user,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/signup", response_model=UserResponse, status_code=201)
async def signup(request: SignupRequest):
    return await signup_user(request.username, request.password)


@router.post("/login", response_model=UserResponse)
async def login(request: LoginRequest):
    return await login_user(request.username, request.password)


@router.put("/{user_id}/onboarding", response_model=UserResponse)
async def onboarding(user_id: str, request: OnboardingRequest):
    return await update_onboarding(
        user_id, request.name, request.experience, request.preferences
    )


@router.get("/{user_id}", response_model=UserResponse)
async def fetch_user(user_id: str):
    return await get_user(user_id)
