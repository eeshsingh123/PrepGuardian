from pydantic import BaseModel, Field


class CandidateProfile(BaseModel):
    name: str
    target_role: str
    target_company: str
    target_level: str
    years_experience: str
    session_date: str


class ConfidenceScore(BaseModel):
    turn: int
    score: float
    note: str


class ConfidenceData(BaseModel):
    scores: list[ConfidenceScore]
    peak_turn: int
    drop_turn: int
    average_score: float
    trend: str


class RadarData(BaseModel):
    pillars: dict[str, float]
    strongest: str
    weakest: str
    avoided: list[str] = Field(default_factory=list)


class MarketGapDimension(BaseModel):
    name: str
    market_bar: float
    candidate_score: float
    gap: float
    verdict: str


class MarketGapData(BaseModel):
    target_role: str
    target_company: str
    target_level: str
    dimensions: list[MarketGapDimension]
    readiness_percentage: int
    readiness_label: str
    summary: str
