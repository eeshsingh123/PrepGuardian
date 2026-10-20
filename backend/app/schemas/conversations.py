from datetime import datetime

from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    role: str
    text: str
    timestamp: datetime


class ConversationSummaryResponse(BaseModel):
    session_id: str
    user_id: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int = 0
    time_limit_seconds: int | None = None
    ended_reason: str | None = None
    turn_count: int = 0
    preview: str = ""


class SessionUsage(BaseModel):
    prompt_tokens: int = 0
    response_tokens: int = 0
    total_tokens: int = 0
    turn_count: int = 0


class ConversationResponse(BaseModel):
    session_id: str
    user_id: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int = 0
    time_limit_seconds: int | None = None
    ended_reason: str | None = None
    turn_count: int = 0
    user_turn_count: int = 0
    agent_turn_count: int = 0
    interview_type: str | None = None
    duration_minutes: int | None = None
    interviewer_notes: list[str] = Field(default_factory=list)
    usage: SessionUsage | None = None
    turns: list[ConversationTurn] = Field(default_factory=list)
    confidence_data: dict | None = None
    radar_data: dict | None = None
    market_gap_data: dict | None = None
    report_text: str | None = None
