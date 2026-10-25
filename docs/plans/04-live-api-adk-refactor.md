# Plan 04 — Live API + ADK Refactor (Keep ADK, Clean It Up)

> Goal: answer "do we have a better alternative than ADK?" with **no — keep ADK `run_live`,
> fix it and migrate models**. Make the live path current, typed, observable, and multi-worker-safe.
> Reference: `backend/app/services/agent_service.py`, `insight_service.py`, `routes/agent.py`,
> `constants.py:10-14`, `config.py:53-58`, `.agents/skills/google-adk-python/references/{streaming,runtime-arch,models}.md`,
> `part5.md` (bidi audio guide). Depends on plan 01 for prompt files; P0 fixes can land first.

## 1. Verdict: keep ADK (don't switch)

- **Keep ADK `run_live` for the interviewer** and **ADK `run_async` Sequential/Parallel for insights**.
  ADK already abstracts exactly what PrepGuardian needs: Live WS lifecycle, `session_resumption`
  (survives 10-min conn resets), `context_window_compression` (needed for 40-min mocks —
  15-min audio / 2-min AV limits otherwise), server VAD + input/output transcription,
  `google_search` grounding, multi-agent insights fan-out. Rewriting on raw `google-genai
  live.connect()` re-creates all of it for no UX gain — ADK passes every `LiveConnectConfig`
  field through via `RunConfig`, so set fields there instead of dropping ADK.
- **Raw `google-genai` Live API** only wins if you need custom `realtime_input_config` beyond ADK
  passthrough, translation/avatar models, or non-ADK transports (SIP/telephony) — none needed today.
- **LiveKit / Pipecat / Agora / Fishjam** (official Live API partners, Sep 2026) only win on
  PSTN/SIP, multi-party, server-side noise-cancel/recording, or >Vertex session quota
  (50 Tier-1 / 1000 Tier-2 concurrent) with fleet autoscaling. For 1:1 browser mic → backend →
  Gemini → playback + 1fps JPEG, they add SFU ops + egress without improving interview quality.
  **Defer until telephony/recording/multi-user requirements land.**
- Edge WebSockets (`routes/agent.py`) stay custom — ADK is only the agent→Google leg. No conflict.

## 2. What's outdated (fix list, Sep–Oct 2026)

| # | Location | Problem | Fix (priority) |
|---|---|---|---|
| P0-1 | `constants.py:14` | `gemini-3.1-flash-lite-preview` **shutdown 2026-05-25** | → `gemini-3.1-flash-lite` (P0) |
| P0-2 | `constants.py:11` | Live `gemini-live-2.5-flash-native-audio` (Vertex 2.5 ID) | → `gemini-3.8-live` default (P0); keep `…-extended-thinking` variant documented for reasoning-heavy sessions |
| P0-3 | `constants.py:13` | `gemini-3.1-pro-preview` still alive but preview | keep short-term, env-overridable; evaluate GA/stable pricing later (P0-env, P2-eval) |
| P0-4 | `config.py:56-58` | `os.environ[PROJECT]=os.getenv(...)` assigns `None` → crash; hardcoded `USE_VERTEXAI=TRUE`, `us-central1` | guarded `if v:` + `LOCATION=os.getenv(..., "us-central1")`; note new `GOOGLE_GENAI_USE_ENTERPRISE` flag (P0) |
| P0-5 | `agent_service.py:88` | `StreamingMode.BIDI` **no-op** on `run_live()` (fails silently) | delete (P0) |
| P0-6 | `agent_service.py:145` | `parts[0]` drops multi-part events on 3.x | `for part in event.content.parts:` (P0) |
| P0-7 | `agent_service.py:305` + `VoiceAgent:374` | bare `audio/pcm` | canonical `audio/pcm;rate=16000` in, 24k out (P0) |
| P1-1 | `agent_service.py:34-40`, `insight_service.py:20` | global `InMemorySessionService` + `Runner`: restart-loss, unbounded, multi-worker-unsafe; dual truth (ADK session vs Mongo tracker) | persistent `DatabaseSessionService` (or documented ephemeral + bounds) + per-app Runner + admission control for concurrent quota (P1) |
| P1-2 | `RunConfig` | no `speech_config` / `realtime_input_config` / `turnCoverage` / `activityHandling` | add `SpeechConfig(Kore/en-US)` + `RealtimeInputConfig{start/end sensitivity, prefixPaddingMs≈20, silenceDurationMs≈300-500}`; decide `turnCoverage` cost with screen share on (P1) |
| P1-3 | `conversation_service.py:108` | `insert_one` same-`session_id` reconnect crashes (unique index) | upsert-or-suffix + `save()` never drops aborts silently (P1) |
| P2-1 | `live_session_service.py` + `agent_service.py:211-215` | Redis `EXPIRE` per audio frame (storm); TTL 90s vs 40-min session | heartbeat both directions + aligned TTL; log `usageMetadata` (P2) |
| P2-2 | `agent_service.py:183-184,309-312` | swallowed exceptions → silent pump death, client hangs | structured errors + metrics + user-visible "reconnecting…" + quota-reject queuing (P2) |
| P2-3 | `db/sqlite.py` + `data/prepguardian.db` | dead SQLite | remove (P2) |
| P2-4 | timer injection `:243-260` | silent `role=user` context pollutes transcript | system-role or metadata channel; exclude from insights input (P2, with plan 01) |

Already current (keep): `response_modalities=[AUDIO]` + dual transcription, `session_resumption={}`,
compression 100k→80k (log recall), fresh `LiveRequestQueue` per session, `close()` in `finally`,
`FIRST_COMPLETED` pump pattern (matches `adk-samples/bidi-demo`).

Live audio facts (Sep 2026): in = 16-bit PCM 16kHz LE mono; out = 24kHz; screen JPEG ≤1fps;
native-audio models = `AUDIO`-only + output transcription for text; 3.8 Live = default low-latency
voice agent model (+ Extended Thinking for background reasoning while talking);
proactive-audio permanently on in 3.8 (setting `false` errors); 97-language auto-detect;
`$0.005/min` in / `$0.018/min` out.

## 3. Target architecture (minimal diff)

```
browser --PCM16k/JPEG/control-frames--> FastAPI WS (/agents/ws/{id})
  --> LiveSessionService (register/heartbeat/remove + admission counter)
  --> SessionRunner (NEW: owns Runner + persistent session_service + RunConfig builder)
       --> ADK run_live --> gemini-3.8-live (Vertex; AI-Studio alias differs — document)
  --> ConversationTracker --> Mongo (source of truth for insights)
```

- `SessionRunner`: thin wrapper replacing module-global `Runner`; builds `RunConfig` from env
  (model, voice, VAD, compression); exposes `start(user_id, session_id)` returning
  `(live_events, queue)`; handles `goAway/sessionResumptionUpdate` surfacing + metrics.
- Session service: `DatabaseSessionService` (Mongo-backed) if available in installed ADK,
  else `InMemorySessionService` with LRU bound + explicit "ephemeral" log; never two truths —
  Mongo transcript remains insights source.
- Config: all models + `GOOGLE_CLOUD_{PROJECT,LOCATION}` + voice/VAD knobs env-driven with
  sane defaults; `config.py` side-effect removed (moved to explicit `init_google_env()` called from lifespan).

## 4. Steps

1. **P0 (do now, ~1 PR)**: model strings → env-overridable (`LIVE_MODEL=gemini-3.8-live`,
   `INSIGHT_FLASH_MODEL=gemini-3.1-flash-lite`); fix `config.py` `None` bug; delete `BIDI`;
   iterate all `parts`; `audio/pcm;rate=16000`; smoke-test 2-min session.
2. **P1**: add `speech_config` + `RealtimeInputConfig`; `SessionRunner` + persistent/bounded sessions +
   admission control; upsert-safe `tracker.save()`; verify `{var?}` interpolation still works with plan 01 suffix.
3. **P2**: heartbeat/TTL alignment + `usageMetadata` logging; structured errors + client reconnect surfacing;
   timer-channel fix; delete SQLite; CORS/prod origins + `.env.example`; load-test 5 concurrent mocks.
4. Update skill refs + `docs/ARCHITECTURE.md` + close debt rows 1-6, 12-16, 24-27.

## 5. Files to touch

- Edit: `constants.py`, `config.py`, `services/agent_service.py:26-40,87-99,112-184,204-312`,
  `services/insight_service.py:20,115-119`, `services/conversation_service.py:72-112`,
  `services/live_session_service.py`, `routes/agent.py:17-60`, `main.py` (lifespan init).
- New: `services/session_runner.py` (or `live_runner.py`); `backend/.env.example` (new).
- Tests: extend `test_live_session_service.py` (reconnect same-id, TTL/heartbeat) +
  `test_insight_pipeline.py` (new model strings resolve); add `test_session_runner.py` (RunConfig builder).

## 6. Acceptance criteria

- [ ] 5-min session on `gemini-3.8-live` completes: audio both ways, transcriptions both ways,
  interruption works, transcript saved, no `parts[0]` loss (multi-part event unit test).
- [ ] Missing `GOOGLE_CLOUD_PROJECT` no longer crashes import; location env-respected.
- [ ] 2nd connect with same `session_id` doesn't 500; server restart doesn't lose Mongo transcripts.
- [ ] `uv run pytest` + `npm run build` green; debt rows for this plan updated.

## 7. Verify

```bash
cd backend && uv run pytest -q
cd frontend && npm run build
# live smoke: 2-min session → interrupt once → share screen 10s → end → transcript has both roles
```
