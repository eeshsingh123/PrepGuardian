from app.interview.tracks import DEFAULT_DURATION_MINUTES, LLD_TRACK
from app.prompts.insights import (
    CONFIDENCE_AGENT_PROMPT,
    MARKET_GAP_AGENT_PROMPT,
    RADAR_AGENT_PROMPT,
    REPORT_COMPILER_PROMPT,
)
from app.prompts.live import (
    AGENT_DESCRIPTION,
    build_clock_cue,
    build_live_instruction,
)
from app.schemas.live import CandidateContext

AGENT_INSTRUCTION = build_live_instruction(
    LLD_TRACK,
    CandidateContext(name="the candidate"),
    DEFAULT_DURATION_MINUTES,
)

__all__ = [
    "AGENT_DESCRIPTION",
    "AGENT_INSTRUCTION",
    "CONFIDENCE_AGENT_PROMPT",
    "MARKET_GAP_AGENT_PROMPT",
    "RADAR_AGENT_PROMPT",
    "REPORT_COMPILER_PROMPT",
    "build_clock_cue",
    "build_live_instruction",
]
