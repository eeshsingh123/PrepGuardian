from pydantic import BaseModel, field_validator

from app.interview.tracks import (
    ALLOWED_DURATIONS_MINUTES,
    DEFAULT_DURATION_MINUTES,
    InterviewType,
)


class CandidateContext(BaseModel):
    name: str = "Not specified"
    experience: str = "Not specified"
    target_company: str = "Not specified"
    target_level: str = "Not specified"
    preferences: str = "Not specified"


class LiveSessionConfig(BaseModel):
    interview_type: InterviewType = InterviewType.LLD
    duration_minutes: int = DEFAULT_DURATION_MINUTES

    @field_validator("duration_minutes")
    @classmethod
    def validate_duration(cls, value: int) -> int:
        if value not in ALLOWED_DURATIONS_MINUTES:
            raise ValueError(f"duration_minutes must be one of {ALLOWED_DURATIONS_MINUTES}.")
        return value

    @property
    def duration_seconds(self) -> int:
        return self.duration_minutes * 60
