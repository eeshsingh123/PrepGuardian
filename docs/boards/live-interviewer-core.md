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
| @flo-8972 Dev 3 — frontend | `dev3/live-core-frontend` | `frontend/src/components/VoiceAgent.tsx`, `frontend/src/components/live/**` (new), `frontend/src/lib/screenFrames.ts` (new), `frontend/src/lib/interviewOptions.ts` (new), `frontend/src/lib/api.ts` (add options call only), `frontend/src/App.css` (live-screen classes only), `frontend/src/components/ConfirmationModal.tsx` (a11y), `frontend/src/App.tsx` (guard nav while live) |

Shared-file order: `backend/app/interview/tracks.py` lent to Dev 2 for review fix R1 (problem bank + phase probes move onto tracks); Dev 1 reads it only.
Lead removes the `AGENT_INSTRUCTION` alias in `app/prompts/__init__.py` after Dev 1 merges. `insight_service.py` import line is Dev 2's only.

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

### Amendment A1 (after UX review; lead applies to Dev 1 branch at merge)
- `session_clock` adds `elapsed_seconds: int` (server-computed). Client counts from frame arrival. `phase_index` is 0-based.
- `GET /agents/interview-options` adds top-level `interviewer_name`. Frontend never hardcodes the name.
- At 0:00 the client shows "Time's up" and sends `session_ended` (`reason: timer_expired`) after a 60 s grace; server does not auto-close.

UX spec for Dev 3: `docs/ux/live-core-slice1.md`.

### Amendment A2 (after real Vertex smoke + Tester 1 round 1) — supersedes the C4 connect step
Why: browser-chosen session ids let one user overwrite another's transcript (T1-D1), JWT in the WS URL lands in
server logs (T1-D8), and Maya never spoke first.
- `POST /agents/sessions` (auth) body `{"interview_type", "duration_minutes"}` → `201 {"session_id", "ticket", "expires_in": 30}`.
  Server generates `session_id` (`sess_` + uuid4 hex). 422 invalid config; 409 `{"detail": "active_session"}` if the user
  already has a live session. Ticket = single-use, 30 s, Redis `pg:ws-ticket:{ticket}` → `{user_id, session_id, interview_type, duration_minutes}`.
- WS `GET /agents/ws?ticket=…` (no path id, no `token`, no config params). Invalid/expired/reused ticket → close 1008 before accept.
- Server opens the interview: sends one non-partial start cue right after the first `session_clock` frame (Maya speaks first, ~10 s).
- Transcript frames gain `"partial": bool` (chunks `true`, final full text `false`). Client: chunks build the live caption,
  final replaces it. Server saves only final text.
- Errors: server sends `{"error": "<code>"}` with `code ∈ {"agent_unavailable", "internal"}` (never raw exception text), then closes 1011.
  Malformed client frames are ignored + logged, never fatal.
- Server stop: at `duration + 60 s` the server sends `{"session_ended": {"reason": "time_limit"}}` and closes 1000. After the
  client's `session_ended` the server saves and closes 1000 (normal end ≠ crash).
- Limits: client frame ≤ 1 MB (else ignored + logged); notes ≤ 40 per session, ≤ 300 chars each; `ended_reason` limited to
  `user_ended | timer_expired`; one live session per user.
- Client UX: after `session_clock`, badge status "Joining…" until the first agent audio chunk.

## Testing (after devs commit)

| Tester | Round 1 | Round 2 (swap) |
|---|---|---|
| @teo-2452 Tester 1 | Dev 1 `dev1/live-core-runtime` | Dev 2, then Dev 3 |
| @dev-8041 Tester 2 | Dev 2 `dev2/live-core-persona` → then Dev 3 | Dev 1 |

Final: both testers run the merged integration branch, incl. a real Vertex smoke session.

## Status
- [x] Base contract committed (lead)
- [x] UX direction received and forwarded (`docs/ux/live-core-slice1.md`)
- [x] Dev 2 committed (69ba79f, review fixes R1 done).
- [x] Tester 2 (@dev-8041) round 1 on Dev 2: sign off with minor issues. D1 (ADK `{}` injection) neutralised by Dev 1's InstructionProvider (ADK bypasses injection for callables) — lead adds regression test. D2–D9 → Dev 2 fix round R2 (in progress); lent `schemas/live.py` for D2/D6.
- [x] Dev 2 R2 fixes committed (0e9054f, 45 tests). Waiting for Tester 1 swap-round sign-off.
- [x] Dev 1 R1 fixes committed (0f76c36, 36 tests): A1, phase-boundary cues with 30 s dedupe, blank profile state. `DEFAULT_TARGET_COMPANY/LEVEL` still used by `routes/conversations.py` → remove in insights task.
- [x] Lead real-Vertex smoke on trial merge: 3.8 Live works; partial cues don't block replies; tools called. Found: no opener, repeat-after-tool-call, doubled transcripts, JWT in logs → Dev 1 R2 (in progress), then A2 rework R3.
- [x] Tester 1 round 1 on Dev 1 (db9a665): BLOCKED — D1 cross-user overwrite (high), D2–D9 medium, D10–D15 low. Report: `docs/qa/live-core-runtime-round1.md` @ teo branch 4771680. → Dev 1 R3 with A2.
- [ ] Tester 1 (@teo-2452) round 2 on Dev 2 (0e9054f) — in progress
- [x] Dev 3 committed (e90811c): god-hook split into 6 focused hooks + orchestrator, beep removed. Follow-up for next frontend task: extract `useLiveSocket` from the 452-line orchestrator.
- [ ] Tester 2 (@dev-8041) round 1 on Dev 3 — in progress (mock backend)
- [ ] Dev 1 committed
- [ ] Tester round 1 / round 2 sign-off
- [ ] Merged one at a time, rebuilt after each
- [ ] Live smoke on Vertex + usage numbers
- [ ] UX sign-off → PR
