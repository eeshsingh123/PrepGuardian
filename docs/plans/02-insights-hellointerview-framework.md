# Plan 02 — Actionable Insights on the HelloInterview LLD Delivery Framework

> Goal: replace generic scores with per-stage LLD scoring that is visual, analytical,
> and grounded in what the candidate actually said.
> Source of rubric: https://www.hellointerview.com/learn/low-level-design/in-a-hurry/delivery
> (Requirements 5m → Entities 3m → Class Design 10-15m → Implementation 10m → Extensibility 5m).
> Depends on: plan 01 (prompt layout + transcript contract fix). Touches backend + frontend + tests.

## 1. Current state (why insights add no value)

- `backend/app/prompts.py:196-399`: confidence rubric is 6 coarse bands with no level anchors;
  radar's 8 pillars (Scalability/Storage/Caching/API/Reliability/Observability/Async/Security)
  measure **solution components**, not **delivery process** — zero scoring for clarifying,
  interfacing, modeling, estimating, prioritizing, verifying.
- No HelloInterview reference anywhere in prompts/skills (only `public/PrepGuardian_Description.md:60`
  links the intro page). The 5-stage framework is **missing as a scored dimension**.
- No evidence grounding: scores have free-text `note` (`schemas/insights.py:13-16`), no
  `turn/timestamp/quote`. Report rule "reference pillar/dim/turn" (`prompts.py:410-411`) is name-dropping.
- **Schema mismatch forces hallucination**: prompts expect `{turn, role: agent|candidate,
  type: question|response|hint|redirect}` (`prompts.py:199-202`) but `routes/conversations.py:77`
  sends `[{role: user|agent, text, timestamp}]` — no turn, no type. Model invents them.
- `market_gap_agent` never sees the transcript (summaries only, `prompts.py:308-312`) — telephone game.
  Bars (`Mid 5s / Senior 7s / Staff 9s`, `prompts.py:324-340`) are invented; `readiness=avg(min(score/bar,1)*100)`
  caps excellence and averages away blocking gaps.
- Frontend (`Transcripts.tsx:626-815`): BarChart has **no market overlay** (`:701` TODO),
  RadarChart single polygon (spec wanted two), Confidence `ReferenceLine y=6` hardcoded
  (`:786`, should be 5.5/7/8.5), no quote display, no jump-to-turn, ReportTab re-implements markdown (`:51-176`).
- `target_role = user.preferences` free text (`routes/conversations.py:71`) → garbage calibration.

## 2. Target design

### 2.1 New scored dimension: `framework_data` (the 5 LLD stages)

Keep the existing 8-pillar radar as **coverage**; add the 5-stage **process** dimension.
New schema (`schemas/insights.py` — add):

```python
class FrameworkEvidence(BaseModel):
    turn: int; timestamp: datetime; quote: str  # quote ≤240 chars, verbatim
class FrameworkSection(BaseModel):
    name: str            # requirements | entities | class_design | implementation | extensibility
    score: float         # 0-10
    bar: float           # level bar (Mid 5.5 / Senior 7 / Staff 8.5, per-section tweak ±0.5)
    gap: float           # bar - score
    verdict: str         # exceeds | meets | close | below
    evidence: list[FrameworkEvidence]  # ≥1 per scored section, [] only if avoided
    missing: list[str]   # concrete missed cues, e.g. "no error-handling question"
    drill: str           # 15-min exercise + what-good-looks-like, level-specific
class FrameworkData(BaseModel):
    sections: list[FrameworkSection]  # exactly 5, in delivery order
    strongest: str; weakest: str; avoided: list[str] = []
```

Per-section must-haves (put in `lld_rubric.py` from plan 01, summarized here):
1. **Requirements**: capabilities? rules/completion? error handling? scope in/out? → confirmed spec + out-of-scope list.
2. **Entities**: nouns→entities with state/rules filter; orchestrator named; ownership (has-a/uses/contains); rules placed with owners. Boxes + arrows, no UML.
3. **Class Design**: per entity top-down State (what it remembers ↔ requirement) + Behavior (small API, each method ↔ requirement); Tell-Don't-Ask.
4. **Implementation**: happy path → edge cases → pseudo-code → 1-2 min verification trace (initial state, tick-by-tick, transitions).
5. **Extensibility**: interviewer twist handled at boundaries, high-level, no rewrite (level-weighted: Junior = attempt counts; Senior/Staff = boundary quality).

### 2.2 Transcript contract fix (required before any new agent)

- `conversation_service.py:45-70` + `routes/conversations.py:77`: emit
  `[{turn: int (1-based), role: user|agent, text, timestamp: ISO, word_count: int}]`.
  `turn` = index in saved `turns` array. Backfill note: old sessions lack turn/word_count —
  frontend must handle missing gracefully; re-running Generate Insights recomputes.
- Update ALL insight prompts to match: `role=user|agent` (never `candidate`), no `type` field,
  evidence must cite `T{turn} @{timestamp} "quote"`.
- Fix `target_role`: add real `target_role` field to onboarding (default "Software Engineer")
  instead of overloading `preferences`; migrate `routes/conversations.py:69-76` builder.
- Deduplicate: `input_transcription` + `text/plain` double-add (`agent_service.py:142-143` vs `:300`) —
  keep server-transcription as canonical, tag client-text as fallback.

### 2.3 Pipeline change

`insight_service.py:55-67`: `Parallel(confidence, radar, framework) → market_gap (reads all three + transcript excerpts) → report`.
- New `framework_agent = LlmAgent(model=PRO, instruction=build_framework_prompt(...), output_schema=FrameworkData, output_key="framework_data", temperature=0)`.
- `market_gap_agent`: must re-read transcript excerpts (not summaries alone); add `blocking_gaps[]`;
  readiness = weighted min-gate: any `below` verdict caps label at `Needs Focused` (no more averaging away failure).
- `report_agent` v2 template (replace `prompts.py:401-492`): per-section card
  `Score | Bar | Gap | What you said (quote+turn) | What bar expects | 1 drill` × 5
  + `Replay timeline` table (Turn | Time | peak/drop/missed-requirement) + keep 8-pillar + market tables.
  Remove "do not add/remove sections" lock for the 5 cards; keep it for the rest.
- Persist `framework_data` in `conversation_service.py:90-106` + `update_conversation_insights:204-237` +
  `ConversationResponse:24-39` + frontend `ConversationFull` type (`api.ts:80-121`).

### 2.4 Frontend: visual + analytical (all in `Transcripts.tsx`, split per plan 03)

1. **Framework stepper**: horizontal 5-step tracker in delivery order, dot color by gap
   (green ≤0 / amber 1-2 / red >2), score + bar under each; click → scrolls to evidence quotes + transcript turn
   (needs turn anchors in `TranscriptTab:463-501`).
2. **Radar 2.0**: two polygons (candidate solid + market dashed — implements `concept-radar.md:117-120` spec);
   BarChart 2.0: candidate bar + per-dimension market marker (fix `:701` with `ComposedChart+Scatter` or custom shape).
3. **Confidence 2.0**: dynamic `ReferenceLine y={5.5|7|8.5 by level}` (fix `:786`); area split above/below bar;
   peak/drop markers with quote popover + `Jump to turn` button.
4. **Action cards**: for weakest 2 sections show `Drill card: title, why it matters for {company Lx},
   15-min exercise, transcript moment to re-do (T{n} link)`.
5. **ReportTab**: replace `parseReportBlocks:51-176` with `react-markdown + remark-gfm`; render the 5 section cards as structured components (not raw markdown tables).
6. **Export**: include `framework_data` JSON alongside `report.md` download (`:346-355`).

## 3. Steps

1. Fix transcript contract (`turn/word_count`), `target_role` field + migration, dedup rule.
2. Add `FrameworkData` schemas + `lld_rubric.py` per-level must-haves.
3. Write `FRAMEWORK_AGENT_PROMPT` (Pro, `temperature=0`, `response_mime_type=json`): score 0-10 × 5 stages,
   require `evidence[{turn,timestamp,quote≤240}]` + `missing[]` + `drill` per section.
4. Harden confidence/radar: `temperature=0`, require `T{turn} @{timestamp} "quote"` in every note/evidence;
   add per-pillar L4/L5/L6 anchors + evidence map.
5. Rewire pipeline to `Parallel(3) → market_gap (reads all + excerpts) → report v2`; persist + serve `framework_data`.
6. Frontend: stepper + radar/bar/confidence 2.0 + action cards + GFM report + turn anchors + export.
7. Backfill: re-run `POST generate-insights` for existing sessions; log `present/missing` (already in `insight_service.py:159-164`).
8. Update `docs/ARCHITECTURE.md` + close debt rows 9/10/17/21/22.

## 4. Files to touch

- Backend: `schemas/insights.py`, `schemas/conversations.py:6-9`, `services/conversation_service.py:45-112,204-237`,
  `routes/conversations.py:69-77`, `services/insight_service.py:23-67,90-176`, `prompts/` (new framework prompt + report v2).
- Frontend: `lib/api.ts:62-121`, `components/Transcripts.tsx` (stepper, charts, cards, GFM, anchors).
- Skill docs: `.agents/skills/insight-generation/*` (add framework agent page).
- Tests: `tests/test_insight_pipeline.py` — new: evidence quotes map to real turns; `type`-hallucination rejected;
  `below` verdict blocks `Ready`; readiness min-gate; report contains 5 cards.

## 5. Acceptance criteria

- [ ] Every framework section score has ≥1 evidence `{turn, timestamp, quote≤240}` resolving to a real transcript turn; no invented `type` fields.
- [ ] Dashboard shows 5-step stepper + per-section gap + 2 drill cards with jump-to-turn links.
- [ ] Radar has 2 polygons; bars show market markers; confidence bar is level-dynamic (5.5/7/8.5).
- [ ] Re-running insights on an old session backfills `framework_data` without losing existing scores.
- [ ] `uv run pytest` + `npm run build` green.

## 6. Verify

```bash
cd backend && uv run pytest -q
cd frontend && npm run build
# manual: pick a session → Generate Insights → check stepper, evidence quotes match Transcript tab turns
```
