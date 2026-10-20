import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import WebSocket
from google.adk.agents import LiveRequestQueue
from google.adk.tools import FunctionTool, ToolContext
from google.genai.types import (
    Behavior,
    Content,
    FunctionResponseScheduling,
    Part,
)

from app import prompts
from app.interview.tracks import PhaseWindow, get_track
from app.schemas.live import CandidateContext, LiveSessionConfig


INTERVIEW_TYPE_STATE_KEY = "interview_type"
DURATION_MINUTES_STATE_KEY = "duration_minutes"
INTERVIEW_STARTED_AT_STATE_KEY = "interview_started_at"
INTERVIEWER_NOTES_STATE_KEY = "interviewer_notes"

CLOCK_CUE_MINUTES = (10, 5, 2)
CUE_DEDUPE_WINDOW_SECONDS = 30

ClockSource = Callable[[], datetime]
SleepSource = Callable[[float], Awaitable[None]]
CueKind = Literal["phase", "minute"]


class InterviewClock:
    """
    Server-owned interview clock for one live session.

    Args:
        config: Validated interview type and duration.
        started_at: Clock start. Defaults to the current UTC time.
        now: Injectable time source, used by tests.
    """

    def __init__(
        self,
        config: LiveSessionConfig,
        started_at: datetime | None = None,
        now: ClockSource | None = None,
    ) -> None:
        self.config = config
        self.track = get_track(config.interview_type)
        self.started_at = started_at or datetime.now(timezone.utc)
        self.now = now or (lambda: datetime.now(timezone.utc))

    @property
    def duration_seconds(self) -> int:
        return self.config.duration_seconds

    @property
    def windows(self) -> list[PhaseWindow]:
        return self.track.schedule(self.duration_seconds)

    @property
    def elapsed_seconds(self) -> int:
        return max(0, int((self.now() - self.started_at).total_seconds()))

    @property
    def remaining_seconds(self) -> int:
        return max(0, self.duration_seconds - self.elapsed_seconds)

    @property
    def current_window(self) -> PhaseWindow:
        return self.track.phase_at(self.elapsed_seconds, self.duration_seconds)

    @property
    def current_phase_index(self) -> int:
        current_key = self.current_window.phase.key
        for index, window in enumerate(self.windows):
            if window.phase.key == current_key:
                return index
        return len(self.windows) - 1

    @property
    def next_window(self) -> PhaseWindow | None:
        index = self.current_phase_index
        if index + 1 >= len(self.windows):
            return None
        return self.windows[index + 1]


def session_config_from_state(state) -> LiveSessionConfig:
    """
    Rebuilds the session config from ADK session state.

    Args:
        state: ADK ToolContext.state or ReadonlyContext.state.
    """
    defaults = LiveSessionConfig()
    return LiveSessionConfig(
        interview_type=state.get(INTERVIEW_TYPE_STATE_KEY, defaults.interview_type),
        duration_minutes=state.get(DURATION_MINUTES_STATE_KEY, defaults.duration_minutes),
    )


def interview_clock_from_state(state, now: ClockSource | None = None) -> InterviewClock:
    """
    Rebuilds the server clock from ADK session state so tool calls stay stateless.

    Args:
        state: ADK ToolContext.state.
        now: Injectable time source, used by tests.
    """
    raw_started_at = state.get(INTERVIEW_STARTED_AT_STATE_KEY)
    started_at = (
        datetime.fromisoformat(raw_started_at)
        if isinstance(raw_started_at, str)
        else None
    )
    return InterviewClock(session_config_from_state(state), started_at=started_at, now=now)


def candidate_context_from_state(state) -> CandidateContext:
    """
    Reads the candidate profile stored in ADK session state. Unknown fields stay
    blank so the live prompt omits them instead of presenting invented facts.

    Args:
        state: ADK ReadonlyContext.state.
    """
    return CandidateContext(
        name=state.get("user_name") or "",
        experience=state.get("user_experience") or "",
        target_company=state.get("user_target_company") or "",
        target_level=state.get("user_target_level") or "",
        preferences=state.get("user_preferences") or "",
    )


def build_clock_state(clock: InterviewClock) -> dict[str, str | int]:
    """
    Builds the ADK session state delta that starts a server-owned interview clock.

    Args:
        clock: Clock created when the WebSocket connection is accepted.
    """
    return {
        INTERVIEW_TYPE_STATE_KEY: clock.config.interview_type.value,
        DURATION_MINUTES_STATE_KEY: clock.config.duration_minutes,
        INTERVIEW_STARTED_AT_STATE_KEY: clock.started_at.isoformat(),
    }


def build_session_clock_payload(clock: InterviewClock) -> dict[str, dict[str, str | int]]:
    """
    Builds the C4 session_clock frame sent to the browser on start and phase changes.

    Args:
        clock: Current server-owned interview clock.
    """
    window = clock.current_window
    return {
        "session_clock": {
            "started_at": clock.started_at.isoformat(),
            "elapsed_seconds": clock.elapsed_seconds,
            "duration_seconds": clock.duration_seconds,
            "phase_key": window.phase.key,
            "phase_title": window.phase.title,
            "phase_index": clock.current_phase_index,
            "phase_count": len(clock.windows),
        }
    }


def get_interview_status(tool_context: ToolContext) -> dict[str, object]:
    """
    Returns elapsed and remaining minutes, the current phase and its goal,
    minutes left in the phase, the next phase, and the saved interviewer notes.
    """
    clock = interview_clock_from_state(tool_context.state)
    window = clock.current_window
    next_window = clock.next_window
    elapsed_seconds = clock.elapsed_seconds
    minutes_left_in_phase = max(0, window.end_seconds - elapsed_seconds)
    return {
        "elapsed_minutes": elapsed_seconds // 60,
        "remaining_minutes": math.ceil(clock.remaining_seconds / 60),
        "phase_key": window.phase.key,
        "phase_title": window.phase.title,
        "phase_goal": window.phase.goal,
        "minutes_left_in_phase": math.ceil(minutes_left_in_phase / 60),
        "next_phase_title": next_window.phase.title if next_window else None,
        "notes": list(tool_context.state.get(INTERVIEWER_NOTES_STATE_KEY) or []),
    }


def save_interview_note(note: str, tool_context: ToolContext) -> dict[str, object]:
    """
    Saves a short agreed fact so it survives context compression. Use it for
    confirmed requirements, entities, and design decisions.
    """
    cleaned_note = note.strip()
    notes = list(tool_context.state.get(INTERVIEWER_NOTES_STATE_KEY) or [])
    if cleaned_note:
        notes.append(cleaned_note)
        tool_context.state[INTERVIEWER_NOTES_STATE_KEY] = notes
    return {"saved": bool(cleaned_note), "note_count": len(notes)}


class ScheduledFunctionTool(FunctionTool):
    """
    Function tool whose Live function response does not start a new spoken turn.

    Args:
        func: Tool callable exposed to the model.
        response_scheduling: Live scheduling mode applied to the function response.
    """

    def __init__(
        self,
        func: Callable[..., Any],
        *,
        response_scheduling: FunctionResponseScheduling,
    ) -> None:
        super().__init__(func)
        self.behavior = Behavior.NON_BLOCKING
        self.response_scheduling = response_scheduling


def build_interview_tools() -> list[ScheduledFunctionTool]:
    """
    Builds the interview tools. Status waits for the model to be idle and note
    saving is silent, so a late function response does not trigger a second turn.
    """
    return [
        ScheduledFunctionTool(
            get_interview_status,
            response_scheduling=FunctionResponseScheduling.WHEN_IDLE,
        ),
        ScheduledFunctionTool(
            save_interview_note,
            response_scheduling=FunctionResponseScheduling.SILENT,
        ),
    ]


class CueScheduler:
    """
    Sends browser phase frames and silent model pacing cues at phase boundaries
    and time milestones without forcing a model turn.

    Args:
        clock: Server-owned interview clock.
        websocket: Browser WebSocket used for session_clock frames.
        live_request_queue: ADK queue used for partial clock cues.
        sleep: Injectable sleep source, used by tests.
    """

    def __init__(
        self,
        clock: InterviewClock,
        websocket: WebSocket,
        live_request_queue: LiveRequestQueue,
        sleep: SleepSource = asyncio.sleep,
    ) -> None:
        self.clock = clock
        self.websocket = websocket
        self.live_request_queue = live_request_queue
        self.sleep = sleep
        self.announced_phase_key: str | None = None

    async def run(self) -> None:
        await self.send_clock_frame()
        self.send_start_cue()
        events = self.build_events()
        minute_cue_times = [
            at_seconds for at_seconds, kind in events if kind == "minute"
        ]
        for at_seconds, kind in events:
            await self.wait_until(at_seconds)
            if kind == "phase":
                await self.send_clock_frame()
                if self.is_near_minute_cue(at_seconds, minute_cue_times):
                    continue
            self.send_cue(self.remaining_minutes())

    def build_events(self) -> list[tuple[int, CueKind]]:
        windows = self.clock.windows
        duration_seconds = self.clock.duration_seconds
        events: list[tuple[int, CueKind]] = [
            (window.start_seconds, "phase") for window in windows[1:]
        ]
        events.extend(
            (duration_seconds - minutes * 60, "minute")
            for minutes in CLOCK_CUE_MINUTES
            if 0 < duration_seconds - minutes * 60 < duration_seconds
        )
        return sorted(events, key=lambda event: event[0])

    def is_near_minute_cue(
        self,
        elapsed_seconds: int,
        minute_cue_times: list[int],
    ) -> bool:
        """
        Avoids stacking a phase cue on a minute cue that is already sent or due
        within the dedupe window. The minute cue always wins.
        """
        return any(
            abs(elapsed_seconds - cue_at) <= CUE_DEDUPE_WINDOW_SECONDS
            for cue_at in minute_cue_times
        )

    def remaining_minutes(self) -> int:
        return math.ceil(self.clock.remaining_seconds / 60)

    def send_start_cue(self) -> None:
        """Sends the non-partial opening cue so the interviewer speaks first."""
        self.live_request_queue.send_content(
            content=Content(
                role="user",
                parts=[Part.from_text(text=prompts.build_session_start_cue())],
            ),
            partial=False,
        )

    async def wait_until(self, elapsed_seconds: int) -> None:
        while self.clock.elapsed_seconds < elapsed_seconds:
            await self.sleep(elapsed_seconds - self.clock.elapsed_seconds)

    async def send_clock_frame(self) -> None:
        window = self.clock.current_window
        if window.phase.key == self.announced_phase_key:
            return
        await self.websocket.send_text(json.dumps(build_session_clock_payload(self.clock)))
        self.announced_phase_key = window.phase.key

    def send_cue(self, remaining_minutes: int) -> None:
        cue_text = prompts.build_clock_cue(
            remaining_minutes,
            self.clock.current_window,
            self.clock.track,
        )
        self.live_request_queue.send_content(
            content=Content(role="user", parts=[Part.from_text(text=cue_text)]),
            partial=True,
        )
