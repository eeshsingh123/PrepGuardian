# Task board — Live Interviewer Core

Integration branch: `feature/live-interviewer-core` (lead merges only). Base commit contains the shared contract.
Research: `docs/research/2026-10-20-gemini-3.8-live.md`. Rules: `AGENTS.md`, `.agents/rules/*`.

## Goal
Move the live interviewer to `gemini-3.8-live`, cut live cost (no 15-s timer turns, smaller context, screen frames
only on change, short prompt), make the interviewer sound human, and let the user pick interview type (LLD / HLD,
both with concurrency) and duration (30 / 45 / 60). Server owns the interview clock.

## Owners (touch only your files; ask the lead for anything else)

| Agent | Branch | Owns |
|---|---|---|
| Lead | `feature/live-interviewer-core` | `backend/pyproject.toml`, `backend/uv.lock`, `backend/app/interview/tracks.py`, `backend/app/schemas/live.py`, `backend/app/schemas/__init__.py`, `docs/**` |
| @nia-1235 Dev 1 — live runtime | `dev1/live-core-runtime` | `backend/app/services/agent_service.py`, `backend/app/services/interview_session.py` (new: clock, tools, cue scheduler), `backend/app/routes/agent.py`, `backend/app/services/conversation_service.py`, `backend/app/schemas/conversations.py`, `backend/app/constants.py`, `backend/app/config.py`, `backend/tests/test_insight_pipeline.py`, `backend/tests/test_interview_session.py` (new), `backend/tests/test_live_session_service.py` |
| @jem-6777 Dev 2 — persona & prompts | `dev2/live-core-persona` | `backend/app/prompts.py` (delete) → `backend/app/prompts/` package (new), `backend/app/services/insight_service.py` (import line only), `backend/tests/test_prompts.py` (new), `.agents/skills/insight-generation/**` (model names only) |
| @flo-8972 Dev 3 — frontend | `dev3/live-core-frontend` | `frontend/src/components/VoiceAgent.tsx`, `frontend/src/components/live/**` (new), `frontend/src/lib/screenFrames.ts` (new), `frontend/src/lib/interviewOptions.ts` (new), `frontend/src/lib/api.ts` (add options call only), `frontend/src/App.css` (live-screen classes only) |

Shared-file order: none — no file has two owners. `insight_service.py` import line is Dev 2's only.

## Contracts (all three build against these; do not change without the lead)

### C1. Interview tracks — `app/interview/tracks.py` (in base)
`InterviewType` (`lld`, `hld`), `ALLOWED_DURATIONS_MINUTES = (30, 45, 60)`, `DEFAULT_DURATION_MINUTES = 45`,
`InterviewTrack.schedule(duration_s)` / `.phase_at(elapsed_s, duration_s)` → `PhaseWindow(phase, start_seconds, end_seconds)`,
`get_track(type)`. Adding a new interview type = add one `InterviewTrack` to `TRACKS`; nothing else should need editing.

### C2. Schemas — `app/schemas/live.py` (in base)
`LiveSessionConfig(interview_type, duration_minutes)` (validated, `.duration_seconds`),
`CandidateContext(name, experience, target_company, target_level, preferences)`.
`InterviewerConstants.NAME = "Maya"`, `.VOICE = "Kore"` in `constants.py`.

### C3. Prompt API — `app/prompts/__init__.py` (Dev 2 provides, Dev 1 consumes)
```python
AGENT_DESCRIPTION: str
def build_live_instruction(track: InterviewTrack, candidate: CandidateContext, duration_minutes: int) -> str
def build_clock_cue(remaining_minutes: int, window: PhaseWindow, track: InterviewTrack) -> str
CONFIDENCE_AGENT_PROMPT, RADAR_AGENT_PROMPT, MARKET_GAP_AGENT_PROMPT, REPORT_COMPILER_PROMPT  # moved unchanged
```
The live instruction references these tools by exact name:
- `get_interview_status()` → `{elapsed_minutes, remaining_minutes, phase_key, phase_title, phase_goal, minutes_left_in_phase, next_phase_title, notes: list[str]}`
- `save_interview_note(note: str)` → `{saved: true, note_count}` — interviewer records key agreed facts (requirements, entities, decisions) so they survive context compression.

### C4. WebSocket (Dev 1 server, Dev 3 client)
- Connect: `/agents/ws/{session_id}?token=…&interview_type=lld|hld&duration_minutes=30|45|60`. Invalid config → close `1008`.
  Connecting = interview starts; server clock starts at accept.
- Client → server: `audio/pcm;rate=16000` (server accepts any `audio/pcm*`), `image/jpeg`, `text/plain`,
  `application/session-control` with `event: session_ended` (+ `reason`). `time_context` and `time_warning` are **removed**.
- Server → client (new): `{"session_clock": {"started_at": ISO8601, "duration_seconds": int, "phase_key": str,
  "phase_title": str, "phase_index": int, "phase_count": int}}` — sent right after start and on every phase change.
  Existing frames unchanged: audio `audio/pcm`, transcript `text/plain` + `is_transcript`, `turn_complete`/`interrupted`, `error`.

### C5. REST (Dev 1 server, Dev 3 client)
`GET /agents/interview-options` (auth required) →
`{"durations_minutes": [30,45,60], "default_duration_minutes": 45, "tracks": [{"type": "lld", "title": "Low-Level Design",
"phases": [{"key", "title", "share", "goal"}]}]}` built from `TRACKS` (so a new track appears in the UI automatically).

## Testing (after devs commit)

| Tester | Round 1 | Round 2 (swap) |
|---|---|---|
| @teo-2452 Tester 1 | Dev 1 `dev1/live-core-runtime` | Dev 2, then Dev 3 |
| @dev-8041 Tester 2 | Dev 2 `dev2/live-core-persona` → then Dev 3 | Dev 1 |

Final: both testers run the merged integration branch, incl. a real Vertex smoke session.

## Status
- [x] Base contract committed (lead)
- [ ] UX direction (@arlo-3414) → forwarded to Dev 3
- [ ] Dev 1 / Dev 2 / Dev 3 committed
- [ ] Tester round 1 / round 2 sign-off
- [ ] Merged one at a time, rebuilt after each
- [ ] Live smoke on Vertex + usage numbers
- [ ] UX sign-off → PR
