# PrepGuardian Architecture — End-to-End Reference

> Generated 2026-10-02 from 5 parallel codebase explorations. Keep updated when contracts change.
> Pair with `AGENTS.md` (memory) and `docs/plans/*` (work).

## 1. Purpose & user journey

PrepGuardian is a live AI mock-interview coach: a student signs up, completes onboarding
(name, experience, target_company, target_level, preferences), starts a live voice +
screen-share session (40-min client timer), receives a real-time AI interviewer, then
reviews the auto-saved transcript and clicks **Generate Insights** for a dashboard
(readiness %, concept radar, confidence curve) + markdown report.

Stated goal (README, `public/PrepGuardian_Description.md`): cure system-design interview
anxiety with an interruptible, screen-aware, profile-calibrated mentor + post-hoc
bar-vs-market analytics. Current direction (this planning round): pivot scoring to the
**HelloInterview LLD delivery framework** (Requirements → Entities → Class Design →
Implementation → Extensibility).

## 2. Repo map

```
backend/main.py                        # FastAPI entry, lifespan, CORS, routers
backend/pyproject.toml                 # py>=3.14, google-adk>=1.26, google-genai>=1.66, motor, redis, fastapi
backend/app/config.py                  # Settings (.env),prod JWT guard, Vertex env side-effect (BUGGY, see §8)
backend/app/constants.py               # App/Model/Auth/Redis constants — model strings live here
backend/app/prompts.py                 # ALL prompts: AGENT_INSTRUCTION (~190 lines) + 4 insight prompts (296 lines)
backend/app/security.py + dependencies.py + logger.py
backend/app/db/mongo.py|redis.py|sqlite.py + __init__.py   # sqlite is DEAD
backend/app/schemas/auth.py|users.py|conversations.py|insights.py
backend/app/services/auth_service.py|user_service.py|agent_service.py|live_session_service.py|conversation_service.py|insight_service.py
backend/app/routes/auth.py|agent.py|users.py|conversations.py
backend/tests/test_auth_service.py|test_insight_pipeline.py|test_live_session_service.py
frontend/src/App.tsx                   # shell + routing + header + theme
frontend/src/main.tsx                  # QueryClient + AuthProvider + Toaster
frontend/src/components/Login.tsx|Onboarding.tsx|VoiceAgent.tsx(669)|Transcripts.tsx(815)|ConfirmationModal.tsx
frontend/src/lib/api.ts(299)|auth.tsx|session.ts|logger.ts
frontend/src/App.css(818) + index.css  # Tailwind 4 + hand-rolled BEM
part5.md (gitignored)                  # ADK bidi-demo audio guide
prepGuardian_architecture.png          # 4-zone system diagram
public/PrepGuardian_Description.md + prompts_written_to_build_this.txt  # product + build log
.agents/rules/, .agents/skills/{frontend-design,google-adk-python,google-genai-sdk-python,insight-generation,ui-ux-pro-max}/
```

No Docker, no CI, no `.env.example`. CORS = `5173` only.

## 3. Backend

### 3.1 Runtime & config

- `main.py:14-20` lifespan `init_databases/close_databases`; `:22-27` FastAPI app;
  `:29-35` CORS; `:37-40` routers (agent, auth, users, conversations); `:43-45` `GET /`.
- `pyproject.toml`: `google-adk>=1.26.0`, `google-genai>=1.66.0`, `fastapi>=0.135.1`,
  `motor>=3.7.1`, `redis>=7.4.0`, `uvicorn`, `pydantic`, `pyjwt`, `bcrypt/pwdlib[argon2]`.
  Resolved (`uv.lock`): adk 1.26.0, genai 1.66.0.
- `config.py:6-29` `Settings`: `MONGO_URI localhost:27017/prepguardian`,
  `SQLITE_DB_PATH data/prepguardian.db`, `REDIS_URL localhost:6379/0`,
  `JWT_SECRET_KEY dev-only…`, cookie flags, `CORS_ORIGINS [5173]`.
  `:31-35` `.env` config. `:37-48` prod JWT guard.
- `config.py:53-58` **import-time side effect**: forces `GOOGLE_GENAI_USE_VERTEXAI=TRUE`,
  `GOOGLE_CLOUD_PROJECT=os.getenv(...)` (assigns `None` → crash if unset),
  `GOOGLE_CLOUD_LOCATION=us-central1`.
- `constants.py`: `APP_NAME prepguardian`, `AGENT_NAME prepguardian_agent`,
  `INSIGHTS_APP_NAME prepguardian_insights`, `RESPONSE_MODALITIES [AUDIO]`,
  `DEFAULT_TARGET_COMPANY/TARGET_LEVEL`, `AGENT_LIVE_MODEL gemini-live-2.5-flash-native-audio`,
  `INSIGHT_PRO_MODEL gemini-3.1-pro-preview`,
  `INSIGHT_FLASH_MODEL gemini-3.1-flash-lite-preview` (dead — shutdown 2026-05-25),
  JWT/Redis constants (`pg_refresh_token`, `pg:live-session`, `pg:revoked-access`, TTL 90s).

### 3.2 Auth & onboarding

- `auth_service.py:21-38` `PasswordService` (argon2 + bcrypt-compat, dummy hash),
  `:41-42` naive-UTC `utc_now`, `:45-93` `TokenService` (access 30m `{sub,jti,iss}`,
  refresh 14d sha256), `:108-211` `AuthService`: signup (`pg_<12hex>`, 409 dup) → session;
  login (timing-mitigated, bcrypt→argon2 upgrade); `create_session` (mint + cookie);
  refresh (rotation, non-atomic); logout (revoke refresh + `SETEX pg:revoked-access:{jti}`).
  Cookie: HttpOnly, `path=/auth`, `max-age 14d`.
- `security.py:17-32` `resolve_user_from_access_token` (decode + revocation + DB),
  `:35-40` `get_current_user`, `:43-51` optional bearer, `:54-64` `get_websocket_user`
  (query `?token=`, else `WS_1008`).
- Routes `auth.py`: `POST /auth/signup|login|token|refresh|logout`, `GET /auth/me`.
- `user_service.py:10-41` `update_onboarding` (`find_one_and_update`, `is_onboarded=True`),
  `:44-51` `get_user`. Route `PUT /users/me/onboarding`
  (`OnboardingRequest`: all 5 fields required, `users.py:25-30`).

### 3.3 Live interview path (ADK `run_live`)

`agent_service.py:26-32` global `root_agent = Agent(model=AGENT_LIVE_MODEL,
instruction=AGENT_INSTRUCTION(192 lines), tools=[google_search])`;
`:34-40` global `InMemorySessionService` + `Runner(APP_NAME)`.
`start_agent_session(user_id,session_id,db) :43-109`: load user → `user_state` dict →
`get_session else create_session(state)` (resume via `Event(state_delta)`) →
`RunConfig(streaming_mode=BIDI [NO-OP], response_modalities=[AUDIO],
session_resumption={}, context_window_compression{100k→80k},
input/output_audio_transcription={})` → `LiveRequestQueue()` → `runner.run_live(...)`.

`routes/agent.py:17-60` `WS /agents/ws/{session_id}?token=`: fetch redis/db →
`get_websocket_user` → `LiveSessionService.register_session NX EX 90` (dup → `WS_1008`) →
`accept()` → `run_bidirectional_session` → on error `send_text({error})+close(1011)` →
`finally remove_session`.

`run_bidirectional_session :315-368`: `start_agent_session` + `ConversationTracker` →
two tasks (`agent_to_client`, `client_to_agent`) → `FIRST_COMPLETED` → cancel other →
`queue.close()` + `tracker.save()`.

- **Agent→client `:112-184`**: `output_transcription.text` → `{mime:text/plain,data,is_transcript:True}`
  + buffer; `input_transcription.text` → `tracker.add_user_turn`; `content.parts[0]`
  (BUG: drops parts 1..n) → `audio/pcm` → forward base64; `part.text && partial` → forward;
  on `turn_complete|interrupted` → `tracker.add_agent_turn(join(buffer))` + forward flags.
  Exceptions swallowed (log only).
- **Client→agent `:187-312`**: `receive_text→json` + `refresh_session (EXPIRE 90)` per frame.
  `time_context{remaining,elapsed,limit}` → throttled (minute-change or 15s) silent
  `send_content("Silent session timer context… Do not answer directly")` as `role=user`
  (pollutes transcript). `application/session-control`: `session_started→mark_started`,
  `time_warning{sec}→mark_started + send_content("tell candidate N minutes remain")`,
  `session_ended{reason}→mark_ended`. `text/plain→send_content + add_user_turn`.
  `audio/pcm|image/jpeg|png→send_realtime(Blob)` (bare `audio/pcm`, should be `;rate=16000`).
- `ConversationTracker (conversation_service.py:12-112)`: in-mem `turns[{role,text,timestamp}]`,
  `mark_started` (first-write-wins), dedup consecutive identical user turns,
  `save()` skips empty, else `insert_one({session_id*,user_id,started_at,ended_at,
  duration,time_limit,ended_reason,turn_count,user/agent counts,turns,insights=None})`.
  Reconnect same `session_id` violates unique index. `get_conversations_by_user :115-165`
  (full-turns fetch for 120-char preview — wasteful), `get_conversation_by_session :168-201`,
  `update_conversation_insights :204-237` (`$set` non-None only).

### 3.4 Insights pipeline (ADK `run_async`)

`insight_service.py:20` separate global `InMemorySessionService`.
Agents: `confidence(LlmAgent, PRO, output_schema=ConfidenceData, key=confidence_data) :23-29`;
`radar(LlmAgent, FLASH, RadarData, radar_data) :31-37`;
`market_gap(LlmAgent, PRO, MarketGapData, market_gap_data) :39-45`;
`report(LlmAgent, FLASH, NO schema, final_report) :47-52`.
`parallel=ParallelAgent(confidence,radar) :55-58`;
`pipeline=SequentialAgent(parallel → market_gap → report) :60-67`.

Trigger `POST /conversations/{id}/generate-insights (conversations.py:47-97)`:
load + own + `400` if no turns → build `candidate_profile`
(`target_role=user.preferences` — BUG: free text as role; `conversations.py:69-76`) →
`raw_transcript=[t.model_dump()]` (`{role,text,timestamp}`, no turn/type) →
`run_insights_pipeline :90-176`:
`create_session(..._insights, state={candidate_profile:json, target_role/company/level,
session_date, candidate_name, raw_transcript:json.dumps})` → `Runner(...).run_async("Generate insights…")`
(drain events, discard partials) → re-`get_session` → `get_state_dict_value` × 3 +
`normalize_report_text` (strip fences) → return dict or `None` if all missing (partial OK) →
`update_conversation_insights` → `{ok:True}` (client refetches).
`503` if `None`.

Prompts (`prompts.py:196-492`): confidence (per-candidate-turn 0-10 + peak/drop/trend/avg, expects
`{turn,role:agent|candidate,type}` — MISMATCH); radar (8 pillars 0-10 + strongest/weakest/avoided);
market-gap (L4/L5/L6 bars 5/7/9, 6 dims, `gap=bar-score`, `readiness=avg(min(score/bar,1)*100)`,
labels 85/70/55/40 — caps excellence, averages away blocking gaps; reads summaries only, never transcript);
report (fixed 6-section markdown template, `<<placeholders>>` + `{braces}` mixed, "don't add/remove sections").
No `temperature/top_p/seed/thinking` anywhere — nondeterministic extraction.
No caching anywhere (and Live API doesn't support it anyway).

Schemas (`schemas/insights.py:4-49`): `CandidateProfile`, `ConfidenceScore{turn,score,note}`,
`ConfidenceData{scores,peak,drop,avg,trend}`, `RadarData{pillars,strongest,weakest,avoided}`,
`MarketGapDimension{name,bar,score,gap,verdict}`, `MarketGapData{role,company,level,dims,readiness%,label,summary}`.
No enums, no evidence quotes, no score-range validation.

## 4. Frontend

Vite 7.3.1 + React 19.2 + TS 5.9 + react-router 7 + TanStack Query 5 + Tailwind 4 + recharts + react-markdown + lucide + sonner.
Single env `VITE_API_BASE_URL` (`frontend/.env` → `127.0.0.1:8000`).
Routes (`App.tsx:108-127`): `/login|/signup|/onboarding|/ (/→VoiceAgent)|/transcripts|*→/`.
Header (Agent/Transcripts + theme + logout) only when authed & not auth/onboarding.

- `Login.tsx:11-128`: username≥3/password≥8 → `signup|login` → `setSession` → `navigate(is_onboarded?/:onboarding)`.
- `Onboarding.tsx:12-168`: 5 required fields (`TARGET_LEVEL_OPTIONS Mid/Senior/Staff+`),
  prefill, `PUT /users/me/onboarding` → `/`. No steps/skip/validation beyond HTML.
- **No lobby**: `/` mounts `VoiceAgent` directly; WS connects on mount (`setTimeout(0)` StrictMode hack).
- `VoiceAgent.tsx:40-668` (single column): status+timer topbar, orb, subtitle, screen thumbnail,
  controls pill, End Session + `ConfirmationModal`.
  Audio out: lazy `AudioContext(24k)`, `Int16→Float32`, gapless queue (`:296-332`); mute suppresses only.
  Mic in: `getUserMedia({audio:true})` (no EC/NS/AGC/device picker) → `AudioContext(16k)` →
  **deprecated `ScriptProcessor(4096)`** (`:353`) → `Float32→Int16→btoa→{audio/pcm}` (no VAD/level).
  Transcript: single string, overwritten per `is_transcript` (`:262-264`) — no history/user turns live.
  Screen: `getDisplayMedia({video:true})` → detached video → `sendScreenFrame` 1fps JPEG q0.5 ≤1024px.
  Timer: 40m (`:22-24`), lazy-start on first packet, `session_started` + `time_warning(10m,3m)` once each,
  auto `endSession(timer_expired)`; `Time left mm:ss` pill (green→yellow→orange→red).
  `endSession`: `session_ended{reason,elapsed,remaining,limit}` → close everything → `/transcripts`.
  WS: `ws(s)://base/agents/ws/sess_*?token=`; `sendSessionControl/sendUserPayload(+time_context)`;
  inbound: `{error}`, `{interrupted}→stopAudio`, `{audio/pcm}→play`, `{is_transcript}`, `{turn_complete}`.
  No reconnect/backoff/heartbeat; token in URL; client clock trusted.
- `Transcripts.tsx:190-815`: `flex` list (`w-80`, loading/error/**empty `No insight sessions found`**)
  + viewer (empty/spinner/error/`DashboardView`).
  `DashboardView:304-461`: header + meta + `Generate Insights` (`useMutation→invalidate`) +
  `Transcript(.txt)/Report(.md)` blob downloads + tabs `Analysis(default)|Review|Transcript`.
  `TranscriptTab:463-501` bubbles; `ReportTab:503-624` custom `parseReportBlocks:81-176`
  (re-implements markdown — fragile); `InsightsTab:626-815`: readiness hero (`%` + `BarChart`,
  **no market-bar overlay**, `:701` TODO) + `RadarChart` (single polygon, no market polygon) +
  `Strongest/Weakest/Missed` badges + `ComposedChart Area+Line` (**hardcoded `ReferenceLine y=6`**,
  should be 5.5/7/8.5) + `Peak/Drop` footer (no quote, no jump-to-turn).
- `lib/api.ts:15-299`: `resolveApiBaseUrl` (loopback sync), `request()` (Bearer in-mem + `credentials:include` +
  401→refresh→retry once), 8 endpoints; `currentAccessToken` in-mem + `localStorage` flag only.
  `auth.tsx:4-96` single `AuthContext`; theme `isDarkMode` prop-drilled (default true, no persist/system-detect).
- Styling: `index.css` (`@import tailwindcss`, DM Sans) + `App.css:818` BEM + keyframes; dark/light ternaries
  everywhere; `App.css` global import leaks. Icons lucide; no shadcn/radix/zustand/motion/whiteboard libs.
  No `ErrorBoundary`, no route lazy-load, modal no focus-trap/Esc, `aria-live` timer only.

## 5. Data & infra

- Mongo (`db/mongo.py`): `users{user_id*,username*,…profile,is_onboarded}`,
  `refresh_tokens{token_hash*,(user_id,expires_at),expires_at TTL}`,
  `conversations{session_id*,(user_id,started_at desc),…turns,insights}`.
- Redis (`db/redis.py`): `pg:live-session:{uid}:{sid}="active" EX 90 NX` (refresh per client frame —
  `EXPIRE` storm at audio rate; 90s too short for pause, too long for crash) + `pg:revoked-access:{jti}`.
- SQLite (`db/sqlite.py` + `data/prepguardian.db`): connected/closed, never read/written, no schema — delete.
- Indexes sensible (unique user/session/token, TTL, recency). List-view fetches full `turns` (fix with projection/limit).

## 6. External references

- Live model (Sep 2026): default `gemini-3.8-live` (+ `…-extended-thinking` for reasoning),
  legacy `gemini-3.1-flash-live-preview`, `gemini-2.5-flash-native-audio-preview-12-2025`.
  Live billing = per-turn context reprocessing (25 tok/s audio); **caching NOT supported** on Live API.
  Partners (media infra): LiveKit, Pipecat, Agora, Fishjam, Vercel, LangChain.
- LLD delivery framework (`hellointerview.com/learn/low-level-design/in-a-hurry/delivery`):
  Requirements 5m → Entities 3m → Class Design 10-15m → Implementation 10m → Extensibility 5m (level-dependent).
  Details in `AGENTS.md §5` and plan 02.
- Skills: `google-adk-python` (has `references/streaming.md`, `runtime-arch.md`, `models.md` — read before live work),
  `google-genai-sdk-python` (no live ref), `insight-generation` (custom; models listed are stale — code wins),
  `frontend-design`, `ui-ux-pro-max`.

## 7. Test snapshot

`tests/test_auth_service.py|test_insight_pipeline.py|test_live_session_service.py` — unit-only with
fakes (`FakeCollection/FakeRedis/FakeSession`); covers refresh-state read, fence-strip, blank-report→None,
route partial-OK, `503` on `None`, live-save transcript. **Missing**: Mongo/Redis/ADK integration,
WS handshake, cross-user authz negative, evidence grounding, readiness gate.

## 8. Tech-debt register (plan sources)

| # | Location | Issue | Plan |
|---|---|---|---|
| 1 | `constants.py:14` | `…flash-lite-preview` shutdown 2026-05-25 | 04 P0 |
| 2 | `constants.py:11` | Live model 2.5, hardcoded | 04 P0 |
| 3 | `config.py:56-58` | `None` overwrite, hardcoded Vertex/us-central1 | 04 P0 |
| 4 | `agent_service.py:88` | `BIDI` no-op | 04 P0 |
| 5 | `agent_service.py:145` | `parts[0]` drops parts | 04 P0 |
| 6 | `agent_service.py:305` + `VoiceAgent:374` | bare `audio/pcm` | 04 P0 |
| 7 | `prompts.py:3-194` | 190-line mega-prompt, stale market claims, fake memory, `{var?}` maybe uninterpolated | 01 |
| 8 | prompts placeholders | `{raw_transcript}` etc. never `.format()`ed (state-passed) — confusing | 01 |
| 9 | insight prompts | expect `turn/type/candidate` — real is `role user|agent` w/o turn | 02 |
| 10 | market-gap | invented bars, capped readiness, summary-only reasoning | 02 |
| 11 | no `temperature` | nondeterministic extraction | 01/02 |
| 12 | global InMemory+Runner | restart-loss, unbounded, multi-worker-unsafe | 04 P1 |
| 13 | no speech/VAD config | default VAD/voice, clipping risk | 04 P1 |
| 14 | timer as `role=user` | pollutes transcript given to insights | 01/04 |
| 15 | double-count transcript | `input_transcription` + `text/plain` both add turns | 02 |
| 16 | `insert_one` same session | reconnect crash | 04 |
| 17 | `target_role=preferences` | garbage calibration | 02 |
| 18 | `ScriptProcessor` | deprecated, no VAD/level/device select | 03 |
| 19 | no lobby/whiteboard | cold drop, screen-thumb only, fatal for design interviews | 03 |
| 20 | live transcript overwrite | single string, no history | 03 |
| 21 | charts | no market overlay, hardcoded bar 6, no evidence/drills | 02/03 |
| 22 | `parseReportBlocks` | custom markdown, replace with GFM | 02/03 |
| 23 | theming/styling | prop-drilled dark, 818-line CSS, no tokens | 03 |
| 24 | Redis TTL 90s/EXPIRE storm | align TTL + heartbeat | 04 |
| 25 | swallowed exceptions | silent pump death, client hangs | 04 |
| 26 | SQLite dead | remove | 04 |
| 27 | CORS/prod origins | 5173 only | 04 |
