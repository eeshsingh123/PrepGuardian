# Plan 03 — UX Redesign (Engaging, Not One-Dimensional)

> Goal: turn the single-orb + subtitles + corner-thumbnail room and the dense gray
> debrief into an engaging lobby → live → debrief journey.
> Reference: `frontend/src/components/VoiceAgent.tsx (669)`, `Transcripts.tsx (815)`,
> `App.tsx`, `lib/api.ts`, `App.css (818)`. Design help: `.agents/skills/ui-ux-pro-max`,
> `.agents/skills/frontend-design`. May start with mocked insight data before plan 02 lands.

## 1. Current state (why it feels flat)

- **No lobby**: `/` mounts `VoiceAgent` directly; WS connects on mount. No mic/speaker check,
  no what-happens-next, no duration/question choice (hard 40m, `VoiceAgent.tsx:22-24`).
- **Single orb = whole interview**: 180px breathing ball + one overwritten subtitle line
  (`setTranscript` overwrites, `:263`) — no avatars, waveforms, captions history, turn counter,
  user captions, level meter, pause. Screen share is a 220px corner thumbnail @1fps, no
  whiteboard/code/diagram — fatal for design interviews.
- **Tiny chrome**: pill controls + red-outline End (disabled until `hasStarted`, `:648` — users can't exit early),
  tone-shifting timer pill that's easy to miss, no keyboard shortcuts.
- **Debrief density without hierarchy**: `% Ready` + 3 charts + markdown tables in same gray cards;
  custom fragile markdown parser (`parseReportBlocks:51-176`); hardcoded bar (`:786`); no evidence/drills.
- **Auth/onboarding flat**: identical centered cards, no progress/illustration/empty-state delight.
- **Tech debt**: deprecated `ScriptProcessor(4096)` (`:353`, main-thread jank, no EC/NS/AGC/device picker,
  ships silence, denial only logged); WS token in URL, no reconnect/backoff/heartbeat, StrictMode `setTimeout(0)` hack;
  client-clock timer (spoofable); `isDarkMode` prop-drilled 4 layers with duplicated classes;
  global `App.css` leak; no `ErrorBoundary`/lazy routes; modal no focus-trap/Esc.

## 2. Target design (3 phases)

### Phase A — Lobby (new route `/lobby`, replaces cold drop)

- Steps: 1) briefing (what happens in 40m + 5 LLD stages) → 2) device check (mic picker + level meter +
  speaker test + screen-share preview) → 3) focus picker (LLD prompt choice × 3 per level + target company/level confirm) → Start.
- `getUserMedia` permission pre-check with friendly denial + retry; persist device + prompt choice in state.
- Only after Start: create `session_id`, connect WS, enter live room. Kills the StrictMode auto-connect hack.

### Phase B — Live room (rebuild `VoiceAgent.tsx` by splitting)

New structure (each its own file under `components/live/`):
```
Lobby.tsx  MicLevel.tsx  Captions.tsx  TurnList.tsx  TimerPill.tsx
ControlsBar.tsx  ScreenShareView.tsx  Whiteboard.tsx (v1: code/diagram scratchpad)
useLiveSession.ts (WS + reconnect + heartbeat)  useMicWorklet.ts (AudioWorklet + VAD)
useTimer.ts (countdown + warnings)  liveStore.ts (minimal context, replaces 13 refs)
```
- **Captions + turns**: keep last agent caption as subtitle AND append every finalized turn
  (both roles, timestamped) to `TurnList` with stage tags (Requirements/Entities/…).
- **Interviewer presence**: persona avatar + name + stage indicator ("Stage 2/5 — Entities"),
  speaking/listening/idle states, waveform (agent) + level meter (user).
- **Timer**: prominent `mm:ss` + progress ring through 5 stage budgets; `time_warning` toasts at 10m/3m;
  End always enabled (confirm modal stays).
- **Audio**: migrate to `AudioWorkletNode` + client VAD + `audioStreamEnd` after >1s pause;
  `echoCancellation/noiseSuppression/autoGainControl` on; device picker; mute = stop sending.
- **Screen/whiteboard**: enlarge share preview, add v1 scratchpad (code block + simple boxes/arrows canvas —
  no excalidraw dependency yet); note "diagrams are described, not graded" until plan 02 saves screen context.
- **Robustness**: WS reconnect with backoff + heartbeat; `aria-live` captions; keyboard shortcuts
  (M mic, S share, E end); recording-consent indicator; mobile layout (no orb/preview overlap).
- Copy tone from plan 01 persona (human, time-boxed, Socratic).

### Phase C — Debrief (rebuild `Transcripts.tsx` by splitting)

```
components/debrief/ SessionList.tsx  FrameworkStepper.tsx  ReadinessHero.tsx
CoverageRadar.tsx  ConfidenceChart.tsx  DrillCards.tsx  ReportView.tsx (GFM)  TranscriptView.tsx
```
- Header: `Session Debrief` + meta + Generate Insights (progress state, not just spinner) + exports.
- Tabs default `Analysis`: Readiness hero + **FrameworkStepper (5 stages, plan 02 data)** → radar/bar/confidence 2.0 → drill cards.
- `Review`: `react-markdown + remark-gfm` (delete custom parser); section cards as components.
- `Transcript`: turn-numbered bubbles with anchors (`#turn-12`) for jump-to-turn from charts/cards.
- Empty/loading/error states everywhere incl. delightful `No sessions yet — run your first mock →` CTA.

### Cross-cutting

- Theming: replace prop-drilled `isDarkMode` with context + persisted preference + system-detect;
  introduce design tokens (replace 818-line bespoke CSS incrementally; keep keyframes).
- Perf: lazy-load `Transcripts` (recharts/markdown) via `React.lazy`; fix `downloadTranscript/Report`
  Firefox quirk (`appendChild`); keep `VITE_API_BASE_URL`-only networking.
- Keep backend contracts unchanged except plan 02's `framework_data` + turn anchors (coordinate).

## 3. Steps

1. Add `/lobby` + device check + focus picker; defer WS connect to Start.
2. Split `VoiceAgent.tsx` → `live/` files; add captions + turn list + stage indicator + timer ring.
3. AudioWorklet migration + VAD + device picker + level meter.
4. WS hook: reconnect/backoff/heartbeat; move token out of URL if backend allows (else keep + note).
5. Whiteboard v1 scratchpad + enlarged share view.
6. Split `Transcripts.tsx` → `debrief/` files; stepper + charts 2.0 (with plan 02 data or mocks) + GFM report + anchors.
7. Theming context + tokens; lazy routes; `ErrorBoundary`; a11y pass (focus-trap modal, Esc, `aria-live`).
8. Update `docs/ARCHITECTURE.md` frontend section + close debt rows 18/19/20/21/22/23.

## 4. Files to touch

- New: `components/live/*`, `components/debrief/*`, `hooks/*` as above; edit `App.tsx` (routes `/lobby`, lazy),
  `lib/api.ts` (types only if plan 02 lands), `index.css` (tokens).
- Do NOT change WS frame shapes or REST paths in this plan (backend plans own those).

## 5. Acceptance criteria

- [ ] New user can complete lobby → 2-min live session (captions + turns accrue, timer visible, mic meter moves)
  → end → debrief with stepper/charts/drills, with zero console errors.
- [ ] No `ScriptProcessor` remains; mic denial shows friendly error; End enabled pre-start.
- [ ] `VoiceAgent.tsx`/`Transcripts.tsx` each <200 lines (logic moved to sub-files).
- [ ] Lighthouse/a11y: modal trappable, captions `aria-live`, mobile 390px usable.
- [ ] `npm run build` green; backend untouched (or only types).

## 6. Verify

```bash
cd frontend && npm run build
# manual: /lobby → allow mic → start → speak 30s → share screen → end → /transcripts checks
```
