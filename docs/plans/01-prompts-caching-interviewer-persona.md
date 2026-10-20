# Plan 01 — Prompts, Caching & Interviewer Persona

> Goal: kill the 190-line mega-prompt, set up correct caching, make the mock
> interviewer sound like a human interviewer, not a narrator.
> Reference: `backend/app/prompts.py` (all of it), `backend/app/constants.py:10-14`,
> `backend/app/services/agent_service.py`, `backend/app/services/insight_service.py`,
> `.agents/skills/google-adk-python/references/streaming.md`.

## 1. Current state (why this hurts)

- `prompts.py:3-194` `AGENT_INSTRUCTION`: ~190 lines doing coach + interviewer + therapist +
  market analyst. Contains stale guarantees (`prompts.py:130-135` hiring freezes/comp — will hallucinate),
  fake memory (`prompts.py:35-36` "I remember you mentioned X" with no retrieval tool),
  `{user_name?}` templating that may never interpolate (ADK `{var?}` vs `{var}` — verify).
- `tools=[google_search]` always attached (`agent_service.py:31`) with "search first, don't hallucinate"
  but no scoping rules.
- Insight prompts use `{raw_transcript}/{candidate_profile}/…` placeholders
  (`prompts.py:242,302,396-398,488-491`) that are **never `.format()`ed** — data arrives via ADK
  session state (`insight_service.py:100-113`). Dead placeholders confuse editors.
- No `temperature/top_p/seed` anywhere — extraction runs hot and nondeterministic.
- **Caching truth (important — correct the assumption in the request):**
  Live API supports **neither explicit nor implicit caching** (docs + forum 2026-07-14).
  Cost control for live = short prompts + `ContextWindowCompressionConfig` (already 100k→80k)
  + turn discipline. Explicit `CachedContent` / implicit caching **only** apply to the
  insights `generateContent`/`run_async` path — implement it there, not on live.

## 2. Target design

### 2.1 File layout (new)

```
backend/app/prompts/
  __init__.py               # re-exports, keeps `from app.prompts import X` working
  live_prefix.py            # STATIC_PREFIX: role, voice rules, LLD stage playbook, screen rules (~60 lines, cacheable conceptually)
  live_suffix.py            # build_live_suffix(profile, level, company) -> dynamic ~25 lines (asked-question state, time budget, level bar)
  live_persona.py           # human-interviewer behaviors (Socratic ladder, backchannels, interruption policy, time-box phrases)
  insight_prompts.py        # move CONFIDENCE/RADAR/MARKET_GAP/REPORT here, each split STATIC + DYNAMIC builder
  lld_rubric.py             # shared LLD stage definitions (names, time budgets, per-level must-haves) reused by live + insights
```

Keep old `prompts.py` as a thin shim re-exporting for one release, then delete.

### 2.2 Live prompt: static prefix + dynamic suffix

- **STATIC_PREFIX** (~60 lines max, rarely changes): who you are (LLD interviewer, not coach);
  voice discipline (1 question at a time, ≤25 words per turn, no markdown aloud, no bullet reading);
  LLD stage playbook with time budgets (Requirements 5m → Entities 3m → Class Design 10-15m →
  Implementation 10m → Extensibility 5m); screen rules (reference what you see, call out by name);
  tool rules (google_search ONLY for company process/comp freshness, never for design answers).
- **DYNAMIC_SUFFIX** (built per session): `Name/Level@Company | asked-so-far | current stage |
  remaining minutes | 1 next move`. Built in Python from ADK state + `ConversationTracker`,
  NOT by the LLM. This is what makes prompts short and cache-shaped on the insights side.
- Delete: market-freeze/comp knowledge claims, fake long-term memory, textbook question banks
  (`prompts.py:65-93` → replace with 3 sample LLD prompts per level, chosen by suffix builder).

### 2.3 Human interviewer persona (anti-artificial checklist)

Implement as explicit instructions in `live_persona.py` + few-shot openers:
- Speak first with a 2-sentence opener using real profile fields only (never invent history).
- One question at a time; acknowledge answers in ≤10 words before moving on ("Got it — Board owns placement.").
- Socratic ladder: hint → narrow → teach, max 2 hints then model the move and move on.
- Time-box aloud: "2 minutes left on requirements — let's lock scope." (driven by `time_context`, not wall-clock guessing).
- Screen grounding: name what you see ("your `Game.makeMove` returns bool — walk me through the false paths").
- Barge-in friendly: yield on interruption, never talk over; no monologues >30s.
- Level calibration: Junior = scaffold heavily; Mid = demand trade-offs; Senior/Staff = push extensibility twists early.
- Never: narrate internal reasoning, read lists aloud, say "as an AI", sycophantic praise, multi-part questions.

### 2.4 Insights caching + determinism (the only place caching applies)

- Add `GenerateContentConfig(temperature=0, top_p=0.9)` (or ADK per-agent config equivalent)
  to `confidence_agent`, `radar_agent`, `market_gap_agent` in `insight_service.py:23-45`.
  Report agent: `temperature=0.3` for readable prose.
- Refactor each insight prompt to **prefix-stable** form: static rubric text first (unchanged across calls),
  transcript/profile appended last. This maximizes implicit-cache hit rate on `gemini-3.1-*`
  (auto ≥4096 tokens) — log `usageMetadata.total_cached_tokens` to prove it.
- If transcripts are routinely large, add explicit `CachedContent` for the static rubric with
  `expire_time` 1h (only if measured hit rate justifies it — transcripts vary, so default to implicit).
- Fix placeholder confusion: builders take typed args (`build_confidence_prompt(transcript_json)`)
  instead of `{raw_transcript}` string templates. Require `output_schema` + `response_mime_type=application/json`
  everywhere (report stays free-markdown but with strict section parser — plan 02).

### 2.5 Model strings (do with plan 04 P0 if 04 lands first)

- Env-overridable: `AGENT_LIVE_MODEL = os.getenv("LIVE_MODEL", "gemini-3.8-live")`,
  `INSIGHT_PRO_MODEL = os.getenv("INSIGHT_PRO_MODEL", "gemini-3.1-pro-preview")`,
  `INSIGHT_FLASH_MODEL = os.getenv("INSIGHT_FLASH_MODEL", "gemini-3.1-flash-lite")`
  (note: drop `-preview` — shutdown 2026-05-25). Single home in `constants.py`.

## 3. Steps

1. Create `backend/app/prompts/` files above; move + trim prompts (prefix ≤60 lines, suffix builder).
2. Wire `agent_service.py:26-32` to `instruction=STATIC_PREFIX` + per-session suffix via state;
   keep state keys `user_name/experience/preferences/target_company/target_level`; verify `{var?}` interpolation with a live smoke test.
3. Scope `google_search`: document when to call (company loop/comp freshness only); remove "search first" blanket order.
4. Add generation configs (`temperature=0` extraction) + `response_mime_type` where ADK supports it.
5. Restructure insight prompts to prefix-stable builders; add cached-token logging.
6. Env-var-ize models in `constants.py`; update `.agents/skills/insight-generation/*` model names.
7. Delete dead placeholders; keep `prompts.py` shim for one release.
8. Update `docs/ARCHITECTURE.md` prompt section + close debt rows 7/8/11.

## 4. Files to touch

- New: `backend/app/prompts/*.py` (5 files). Edit: `backend/app/services/agent_service.py:26-32,56-63`,
  `backend/app/services/insight_service.py:23-52`, `backend/app/constants.py:10-14`,
  `.agents/skills/insight-generation/SKILL.md + references/*` (model names only).
- Tests: extend `backend/tests/test_insight_pipeline.py` — assert prompts contain no `{raw_transcript}`
  leftovers, suffix builder output ≤800 chars, configs `temperature==0` for extraction agents.

## 5. Acceptance criteria

- [ ] Live instruction assembled = prefix (static, ≤60 lines) + suffix (dynamic, ≤25 lines); no mega-prompt import.
- [ ] 5-min dry-run transcript reads human: ≤25 words/turn avg, 1 question/turn, ≥3 time-box callouts per 40m, zero "as an AI".
- [ ] Insights agents run with `temperature=0` (extraction) and prefix-stable prompts; cached-token log line emitted per run.
- [ ] No `{var}` placeholders that are never formatted; `uv run pytest` + `npm run build` green.

## 6. Verify

```bash
cd backend && uv run pytest -q
cd frontend && npm run build
# live smoke: start server, run 2-min session, check suffix state + turn word counts
```
