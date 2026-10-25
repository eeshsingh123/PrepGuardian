# AGENTS.md — PrepGuardian Memory & Working Rules

> Read this first on every new session. Source of truth for what PrepGuardian is,
> how it runs, and what not to break. Deep dive: `docs/ARCHITECTURE.md`.
> Implementation plans: `docs/plans/00-OVERVIEW.md` → `01..04`.

## 1. What this app is

PrepGuardian = live AI mock-interview coach for students. Flow:
`signup/login → onboarding (name, experience, target_company, target_level, preferences)
→ live voice + screen-share mock interview (40-min timer) → transcript saved to Mongo
→ on-demand Generate Insights → dashboard (readiness %, radar, confidence) + markdown report`.

- Intent is **Low-Level Design (LLD) interview prep** scored against the
  HelloInterview LLD delivery framework (see §5). The current code is still
  system-design-flavored — plans 01/02 migrate it to LLD.
- Single developer, vibe-coded, Antigravity IDE + Gemini. Expect slop: dead code,
  190-line mega-prompt, duplicated logic. Clean as you touch.

## 2. Stack & entry points

| Layer | Tech | Entry |
|---|---|---|
| Live agent | Google ADK `run_live` + Gemini Live API | `backend/app/services/agent_service.py` |
| Batch insights | ADK `SequentialAgent(Parallel(confidence, radar) → market_gap → report)` | `backend/app/services/insight_service.py` |
| API | FastAPI + uvicorn, `uv` (never pip) | `backend/main.py`, `backend/app/routes/{auth,agent,users,conversations}.py` |
| DB | MongoDB Motor (primary), Redis (ephemeral), SQLite (DEAD — do not use) | `backend/app/db/` |
| Frontend | Vite 7 + React 19 + TS + react-router + TanStack Query + Tailwind 4 + recharts | `frontend/src/{App.tsx,components/VoiceAgent.tsx,components/Transcripts.tsx,lib/api.ts}` |
| WS | Browser ↔ FastAPI `/agents/ws/{session_id}?token=` ↔ ADK ↔ Gemini | `backend/app/routes/agent.py:17-60` |

Models (Oct 2026 — `backend/app/constants.py:10-14`, **must update**, see plan 04):
- Live: `gemini-live-2.5-flash-native-audio` → migrate to `gemini-3.8-live`.
- Insights Pro: `gemini-3.1-pro-preview` (confidence, market-gap).
- Insights Flash: `gemini-3.1-flash-lite-preview` (**SHUTDOWN 2026-05-25** → `gemini-3.1-flash-lite`).

## 3. Critical contracts (do not break)

1. **Auth**: JWT access (30m, in-memory frontend) + rotating HttpOnly refresh cookie
   (`pg_refresh_token`, path `/auth`). WS auth = `?token=` query param.
   Code: `backend/app/services/auth_service.py`, `backend/app/security.py`.
2. **Transcript shape** (today): `[{role: user|agent, text, timestamp}]` — NO `turn` index,
   NO `type` field. Prompts that expect `{turn, role: agent|candidate, type: question|response|hint|redirect}`
   are **wrong** and cause hallucination (`backend/app/prompts.py:196-243`, `backend/app/routes/conversations.py:77`).
   Plan 02 fixes the contract to `[{turn, role, text, timestamp, word_count}]`.
3. **ADK state keys** for live personalization: `user_name, user_experience, user_preferences,
   user_target_company, user_target_level` (`agent_service.py:56-63`). Prompt template uses
   `{var?}` optional syntax (`prompts.py:188-194`).
4. **Insight state keys**: `candidate_profile, raw_transcript, confidence_data, radar_data,
   market_gap_data, final_report` (`insight_service.py:100-148`). Report agent has NO output_schema (free markdown).
5. **Audio contract**: mic in = 16-bit PCM 16kHz mono base64 (`audio/pcm`, canonical `audio/pcm;rate=16000`);
   agent out = 24kHz. Screen = JPEG ≤1024px @1fps. Frontend uses deprecated `ScriptProcessorNode`
   (`VoiceAgent.tsx:353`) — plan 03 migrates to AudioWorklet.
6. **Timer**: client-owned 40-min countdown (`VoiceAgent.tsx:22-24`), `session_started / time_warning(10m,3m) /
   session_ended` control frames + silent `time_context` injection (`agent_service.py:204-262`).
   Do not trust client time server-side for scoring.

## 4. Known landmines (check before editing)

- `backend/app/config.py:56-58` overwrites `GOOGLE_CLOUD_PROJECT` with `None` if env missing + hardcodes
  `USE_VERTEXAI=TRUE`, `us-central1`. Fix with guarded `if v:` + env location.
- `agent_service.py:88` `StreamingMode.BIDI` is a **no-op** on `run_live()` — safe to delete.
- `agent_service.py:145` `parts[0]` drops multi-part events on 3.x models — iterate all parts.
- `agent_service.py:305` bare `audio/pcm` should be `audio/pcm;rate=16000`.
- **Live API has NO prompt/context caching** (explicit or implicit). Cost control = short prompts +
  `ContextWindowCompressionConfig(trigger 100k / target 80k)` + turn discipline — NOT caching.
  Caching only applies to the insights (`generateContent`) path.
- Global `InMemorySessionService` + `Runner` (`agent_service.py:34-40`, `insight_service.py:20`) =
  lost on restart, unbounded, multi-worker-unsafe. Plan 04 replaces with persistent sessions.
- `conversation_service.py:108` `insert_one` with unique `session_id` index — reconnect with same id crashes.
- `routes/conversations.py:71` `target_role = user.preferences` (free text!) — semantic bug, plan 02 fixes.
- `Transcripts.tsx:701` BarChart has no market-bar overlay; `:786` hardcoded `ReferenceLine y=6`
  (should be 5.5/7/8.5 by level). `parseReportBlocks:51-176` re-implements markdown — replace with GFM.
- No Docker, no CI, no `.env.example`. CORS only allows `5173`. `data/prepguardian.db` is orphaned.

## 5. HelloInterview LLD delivery framework (insights rubric — plan 02)

Source: `https://www.hellointerview.com/learn/low-level-design/in-a-hurry/delivery`.
Score **each** section 0–10 with `evidence:[{turn, timestamp, quote≤240ch}]` + `missing[]` + 15-min `drill`:

1. **Requirements (~5m)** — primary capabilities; rules/completion; error handling; scope in/out. Output: confirmed spec + out-of-scope list.
2. **Entities & Relationships (~3m)** — nouns→entities filter (state/rules = entity, else field); orchestrator; ownership (has-a/uses/contains); where rules live. Output: boxes + arrows, no UML.
3. **Class Design (~10–15m)** — per entity top-down: State (what it remembers) + Behavior (small API, each method ↔ requirement). Tell-Don't-Ask, rules with state owner.
4. **Implementation (~10m)** — happy path → edge cases → pseudo-code → 1–2 min verification trace (initial state, tick-by-tick, transitions).
5. **Extensibility (~5m, level-dependent)** — interviewer-led twist; point to boundaries; stay high-level, no rewrite.

Keep the existing 8-pillar component radar (Scalability/Storage/Caching/API/Reliability/Observability/Async/Security)
as **orthogonal coverage**; the 5-stage framework above is the new **process** dimension.

## 6. Working rules

- Backend: `uv` only; async Motor; `snake_case`; typed + Pydantic; one DB init; fail-fast (`HTTPException`),
  minimal try/except; `backend/app/logger.py` logger, info default, no over-logging; secrets via env only.
  Full rules: `.agents/rules/backend-code-rule.md`.
- Frontend: split bloated components (`VoiceAgent 669` / `Transcripts 815` lines must be modularized);
  responsive; `VITE_API_BASE_URL` only, no hardcoded URLs; no secrets in payload; readable diffs for a
  frontend beginner. Full rules: `.agents/rules/frontend-code-rule.md`.
- Prompts: concise + actionable, no mega-prompts; static prefix (cacheable) / dynamic suffix split;
  `temperature=0` for extraction; every score grounded in `T{turn} @{timestamp} "quote"`.
- UX: lobby → live (captions + turns + timer + whiteboard) → debrief (stepper + evidence + drills).
  No silent failures; every async op has loading/error/empty states.
- Ask when ambiguous; never assume; never commit/push unless asked. Verify with
  `uv run pytest` (backend) and `npm run build` (frontend) before finishing.

## 7. GitHub & history

- Remote: `https://github.com/eeshsingh123/PrepGuardian.git`.
- HEAD (Oct 2026): `6af7ec6 Timer context…` on `feat/ux-timer-integration` (dirty tree).
  Prior: auth revamp (JWT+sticky), constants cleanup, arch diagram, insight-generation `#1 #2`.
- Build log: `public/prompts_written_to_build_this.txt`; product notes: `public/PrepGuardian_Description.md`.
- `part5.md` (gitignored) = ADK bidi-demo audio guide; `prepGuardian_architecture.png` = system diagram.

## 8. Where to work

Pick ONE file from `docs/plans/` and implement end-to-end (backend + frontend + tests):
`00-OVERVIEW.md` (read first) → `01-prompts-caching-interviewer-persona.md` →
`02-insights-hellointerview-framework.md` → `03-ux-redesign.md` → `04-live-api-adk-refactor.md`.
Each plan lists scope, files, steps, acceptance criteria, and verification commands.
