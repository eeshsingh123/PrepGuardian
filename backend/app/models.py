from datetime import datetime
from pydantic import BaseModel, Field


# ─── Auth Requests ───

class SignupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=4, max_length=100)


class LoginRequest(BaseModel):
    username: str
    password: str


class OnboardingRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    experience: str = Field(..., min_length=1, max_length=200)
    preferences: str = Field(..., max_length=2000)


# ─── User Response ───

class UserResponse(BaseModel):
    """
    Safe user response excluding sensitive fields like password_hash.
    Returned to frontend after signup, login, and profile fetch.
    """
    user_id: str
    username: str
    name: str | None = None
    experience: str | None = None
    preferences: str | None = None
    is_onboarded: bool = False
    created_at: datetime


# ─── Conversation Models ───

class ConversationTurn(BaseModel):
    """Single turn in a conversation — either user or agent."""
    role: str  # "user" or "agent"
    text: str
    timestamp: datetime


class ConversationSummaryResponse(BaseModel):
    """
    Lightweight model used for listing conversations. Includes a preview
    of the first agent message so the user can identify the conversation.
    """
    session_id: str
    user_id: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int = 0
    turn_count: int = 0
    preview: str = ""
    # Simple boolean flags or partial data could be added here if needed for icons on the list, 
    # but to minimize payload, we'll keep the full data in the detailed response.


class ConversationResponse(BaseModel):
    session_id: str
    user_id: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int = 0
    turn_count: int = 0
    user_turn_count: int = 0
    agent_turn_count: int = 0
    turns: list[ConversationTurn] = []
    confidence_data: dict | None = None
    radar_data: dict | None = None
    market_gap_data: dict | None = None
    report_text: str | None = None
