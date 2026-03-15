import uuid
from datetime import datetime, timezone

import bcrypt
from fastapi import HTTPException

from app.db.mongo import get_mongo_db
from app.logger import logger
from app.models import UserResponse


def generate_user_id() -> str:
    return f"pg_{uuid.uuid4().hex[:8]}"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


async def signup_user(username: str, password: str) -> UserResponse:
    """
    Creates a new user in MongoDB. Generates a unique user_id and hashes
    the password before storing.

    Args:
        username: Unique username chosen by the user.
        password: Plaintext password to be hashed.

    Returns:
        UserResponse with the newly created user's details.

    Raises:
        HTTPException 409: If the username is already taken.
    """
    db = get_mongo_db()
    existing = await db.users.find_one({"username": username})
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken.")

    now = datetime.now(timezone.utc)
    user_doc = {
        "user_id": generate_user_id(),
        "username": username,
        "password_hash": hash_password(password),
        "name": None,
        "experience": None,
        "target_company": None,
        "target_level": None,
        "preferences": None,
        "is_onboarded": False,
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(user_doc)
    logger.info(f"User '{username}' created with ID '{user_doc['user_id']}'.")
    return UserResponse(**{k: v for k, v in user_doc.items() if k != "password_hash"})


async def login_user(username: str, password: str) -> UserResponse:
    """
    Authenticates a user by verifying their username and password.

    Args:
        username: The username to authenticate.
        password: The plaintext password to verify.

    Returns:
        UserResponse with the authenticated user's details.

    Raises:
        HTTPException 401: If credentials are invalid.
    """
    db = get_mongo_db()
    user_doc = await db.users.find_one({"username": username})
    if not user_doc or not verify_password(password, user_doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    return UserResponse(**{k: v for k, v in user_doc.items() if k != "password_hash"})


async def update_onboarding(
    user_id: str,
    name: str,
    experience: str,
    target_company: str,
    target_level: str,
    preferences: str,
) -> UserResponse:
    """
    Updates the user's profile with onboarding information and marks
    the user as onboarded.

    Args:
        user_id: The backend-generated user ID.
        name: User's display name.
        experience: User's experience level description.
        preferences: Free-text learning preferences.

    Returns:
        UserResponse with the updated user details.

    Raises:
        HTTPException 404: If the user is not found.
    """
    db = get_mongo_db()
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
                "updated_at": datetime.now(timezone.utc),
            }
        },
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="User not found.")

    logger.info(f"User '{user_id}' onboarding completed.")
    return UserResponse(**{k: v for k, v in result.items() if k != "password_hash"})


async def get_user(user_id: str) -> UserResponse:
    """
    Fetches a user by their backend-generated user_id.

    Args:
        user_id: The backend-generated user ID.

    Returns:
        UserResponse with the user's details.

    Raises:
        HTTPException 404: If the user is not found.
    """
    db = get_mongo_db()
    user_doc = await db.users.find_one({"user_id": user_id})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found.")

    return UserResponse(**{k: v for k, v in user_doc.items() if k != "password_hash"})
