from datetime import UTC, datetime

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.logger import logger
from app.schemas import UserPublic
from app.services.auth_service import user_from_doc


async def update_onboarding(
    user_id: str,
    name: str,
    experience: str,
    target_company: str,
    target_level: str,
    preferences: str,
    db: AsyncIOMotorDatabase,
) -> UserPublic:
    result = await db.users.find_one_and_update(
        {"user_id": user_id},
        {
            "$set": {
                "name": name,
                "experience": experience,
                "target_company": target_company,
                "target_level": target_level,
                "preferences": preferences,
                "is_onboarded": True,
                "updated_at": datetime.now(UTC).replace(tzinfo=None),
            }
        },
        return_document=True,
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    logger.info("User '%s' onboarding completed.", user_id)
    return UserPublic.model_validate(user_from_doc(result))


async def get_user(user_id: str, db: AsyncIOMotorDatabase) -> UserPublic:
    user_doc = await db.users.find_one({"user_id": user_id})
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return UserPublic.model_validate(user_from_doc(user_doc))
