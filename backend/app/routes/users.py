from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import DatabaseDep
from app.schemas import OnboardingRequest, UserPublic
from app.security import get_current_user
from app.services.user_service import update_onboarding


router = APIRouter(prefix="/users", tags=["Users"])


@router.put("/me/onboarding", response_model=UserPublic)
async def onboarding(
    request: OnboardingRequest,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    db: DatabaseDep,
) -> UserPublic:
    return await update_onboarding(
        current_user.user_id,
        request.name,
        request.experience,
        request.target_company,
        request.target_level,
        request.preferences,
        db,
    )
