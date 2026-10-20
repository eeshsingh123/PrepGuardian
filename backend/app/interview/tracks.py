from dataclasses import dataclass
from enum import StrEnum


class InterviewType(StrEnum):
    LLD = "lld"
    HLD = "hld"


ALLOWED_DURATIONS_MINUTES = (30, 45, 60)
DEFAULT_DURATION_MINUTES = 45


@dataclass(frozen=True)
class Phase:
    key: str
    title: str
    share: float
    goal: str
    probe: str = ""


@dataclass(frozen=True)
class PhaseWindow:
    phase: Phase
    start_seconds: int
    end_seconds: int


@dataclass(frozen=True)
class InterviewTrack:
    type: InterviewType
    title: str
    problems: str
    looking_for: str
    phases: tuple[Phase, ...]

    def __post_init__(self):
        total = sum(p.share for p in self.phases)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Phase shares for {self.type} must sum to 1.0, got {total}.")

    def schedule(self, duration_seconds: int) -> list[PhaseWindow]:
        windows = []
        start = 0.0
        for phase in self.phases:
            end = start + phase.share * duration_seconds
            windows.append(PhaseWindow(phase, round(start), round(end)))
            start = end
        return windows

    def phase_at(self, elapsed_seconds: int, duration_seconds: int) -> PhaseWindow:
        windows = self.schedule(duration_seconds)
        for window in windows:
            if elapsed_seconds < window.end_seconds:
                return window
        return windows[-1]


LLD_TRACK = InterviewTrack(
    type=InterviewType.LLD,
    title="Low-Level Design",
    problems="parking lot, rate limiter, or elevator",
    looking_for=(
        "entities with clear state and behavior, small APIs, rules placed with the state they protect, "
        "and a design the candidate can walk through"
    ),
    phases=(
        Phase("requirements", "Requirements", 0.12,
              "Confirm core capabilities, rules, error handling, and what is out of scope."),
        Phase("entities", "Entities & Relationships", 0.08,
              "Pick the real entities, the orchestrator, and who owns what.",
              probe="Ask which noun owns each rule, and drop nouns that are only fields."),
        Phase("class_design", "Class Design", 0.30,
              "Per entity: the state it keeps and a small API where each method maps to a requirement."),
        Phase("implementation", "Implementation", 0.25,
              "Happy path, then edge cases, then a short walkthrough of state changes."),
        Phase("concurrency", "Concurrency", 0.12,
              "Shared state under concurrent access: races, locking, atomicity, thread-safe structures.",
              probe="Ask what is shared, what the lock protects, and what happens when two threads "
              "call the same method."),
        Phase("extensibility", "Extensibility", 0.08,
              "One interviewer twist; candidate points to boundaries without a rewrite."),
        Phase("wrap_up", "Wrap-up", 0.05,
              "Short close and candidate questions."),
    ),
)

HLD_TRACK = InterviewTrack(
    type=InterviewType.HLD,
    title="System Design",
    problems="URL shortener or ticket booking",
    looking_for=(
        "requirements, core entities and API, a working high-level design, and deep dives with trade-offs"
    ),
    phases=(
        Phase("requirements", "Requirements", 0.14,
              "Functional requirements, key non-functional requirements, and rough scale."),
        Phase("entities_api", "Core Entities & API", 0.12,
              "Core entities and the main API endpoints or interfaces."),
        Phase("high_level_design", "High-Level Design", 0.30,
              "A working design that satisfies the functional requirements end to end.",
              probe="Ask them to trace one request end to end."),
        Phase("deep_dives", "Deep Dives", 0.26,
              "Scale, bottlenecks, storage and caching choices with trade-offs.",
              probe="Pick two bottlenecks and ask for trade-offs."),
        Phase("concurrency", "Concurrency & Consistency", 0.12,
              "Races, contention, idempotency, distributed locking, and consistency guarantees.",
              probe="Ask what happens on retries, or when two writers update the same record."),
        Phase("wrap_up", "Wrap-up", 0.06,
              "Short close and candidate questions."),
    ),
)

TRACKS: dict[InterviewType, InterviewTrack] = {track.type: track for track in (LLD_TRACK, HLD_TRACK)}


def get_track(interview_type: InterviewType) -> InterviewTrack:
    return TRACKS[interview_type]
