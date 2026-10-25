# UX spec — Live interviewer core, slice 1 (by @arlo-3414, decisions applied by lead)

Interviewer name always comes from `interviewer_name` in `GET /agents/interview-options` — never hardcode it.
Below, `{Name}` = that value.

## 0. Ground rules
- Stays on `/` inside `VoiceAgent`, a state machine: **setup → connecting → live → ending**. WS connects only on Start.
- New components in `components/live/`: `SetupPanel`, `TrackCard`, `DurationPicker`, `InterviewerBadge`, `SessionTimer`,
  `PhaseProgress`, `ConnectionBanner`. `VoiceAgent.tsx` < 200 lines. Hooks/helpers may live in `components/live/` too.
- Keep the `isDarkMode` prop and `--dark/--light` modifier classes (no theming refactor in this slice).
- Copy: calm, sentence case, no hype. Never "AI", "magic", "supercharge", "the agent".

## 1. States

### 1a. Setup
Desktop (≥641px): centered card, `max-width: 720px`, padding 2rem.
```
Choose your interview
┌ Low-Level Design ───────┐ ┌ System Design ─────────┐
│ 1 Requirements   ~5 min │ │ 1 Requirements  ~6 min │
│ … (all phases)          │ │ …                      │
└─────────────────────────┘ └────────────────────────┘
Length      [ 30 min ][ 45 min ][ 60 min ]
{Name} will run a 45-minute Low-Level Design interview…
                        [ Start interview ]
```
- Track cards: 2-col grid (1-col ≤640px). Title + numbered phases, each `~{round(share × duration)} min`, live-updating
  with length. Phase `goal` not shown.
- Length: segmented control from `durations_minutes`.
- Defaults: last choice from localStorage (`lib/interviewOptions.ts`), else first track + `default_duration_minutes`.
- Mobile 390px: cards stack, length stays one row of three, Start full-width at bottom.

| State | UI |
|---|---|
| Loading options | 2 pulse skeleton cards; length + Start disabled |
| Options failed | "We couldn't load interview options." + **Try again** |
| No tracks | "No interview types are available right now. Please try again later." Start disabled |
| Checking mic (after Start) | Start spinner + "Checking your microphone…" (disabled) |
| Mic denied (`NotAllowedError`) | Under Start: "{Name} can't hear you yet. Allow microphone access from the icon in your browser's address bar, then try again." + **Try again** |
| No mic (`NotFoundError`) | "We couldn't find a microphone. Plug one in and try again." |

- Ask for mic **only on Start**. Mic is **on** when live begins.
- What to expect: "{Name} will run a {N}-minute {track title} interview. Think out loud like you would with a real
  interviewer. Share your screen when you want her to see your diagram or code."

### 1b. Connecting (socket open → first `session_clock`)
- Live layout, disconnected look: dimmed orb, "Connecting to {Name}…", timer `--:--`, phase row "Getting ready…".
- **Cancel** replaces End (no confirm): closes socket, back to setup with choices kept.
- No frame within 15 s → `ConnectionBanner`: "We couldn't reach the interview. Check your connection and try again."
  + **Try again** + **Back to setup**.
- Close code 1008 → setup with "That setup isn't valid anymore. Please choose again."

### 1c. Live
Desktop: column `max-width: 960px`.
```
[M] {Name}                                  ⏱ TIME LEFT 32:14
    Speaking
Phase 3 of 7 — Class Design
▬▬▬ ▬▬ ▬▬▬▬▬▬▬▬░░░░ ▭▭▭▭▭▭ ▭▭▭ ▭▭ ▭
                 ( orb )
           caption text (existing style)
          [share]  [ MIC ]  [speaker]
               [ End interview ]
            M mute · S share · E end
```
- Remove the Wifi "Connected" pill; connection only surfaces via the banner on problems.
- Screen preview 220px, pinned left below the header row (never overlaps badge/timer). Badge "Sharing".
- Mobile 390px: header one row (32px avatar + "{Name} · Speaking" left, time-only timer right); phase row
  "Phase 3 of 7 — Class Design" → "3/7 · Class Design" if it doesn't fit, bar full width below; orb 140px; caption
  max 3 lines; preview hidden (only a "Sharing" pill); shortcut hint hidden; no overlap at 390×700.

**InterviewerBadge**: 40px circle with the name's first letter, card surface, 2px ring: violet `#a78bfa`/`#7c3aed`
speaking, blue `#60a5fa`/`#2563eb` listening, neutral when muted. Status: "Speaking" / "Listening" / "You're muted" / "Connecting…".

**SessionTimer**: reuse `.voice-agent__timer`. On each `session_clock` frame store `elapsed_seconds` + arrival time
(`performance.now()`); `remaining = duration_seconds − (elapsed_seconds + secondsSinceArrival)`, clamped ≥0, per second.
Green >10 min, orange ≤10, red ≤3 (drop yellow). At 0:00 shows "Time's up"; after 60 s grace the client sends
`session_ended` with `reason: "timer_expired"` (unless the server closed first). End stays enabled.

**PhaseProgress**: text `Phase {phase_index+1} of {phase_count} — {phase_title}` (`phase_index` is 0-based).
Segmented bar, one per phase, `flex-grow: share`, height 4px, gap 3px, radius 999px. Done `#9ca3af`/`#6b7280`;
current base `rgba(59,130,246,.25)` fill `#60a5fa`/`#2563eb`; upcoming `rgba(255,255,255,.08)`/`rgba(0,0,0,.08)`.
Server `phase_index` decides current; fill inside current is client-estimated from shares/time, capped 100%.
Segment `title` = "{title} · ~{n} min".

**Controls**: same three + End, **End always enabled**. Share titles "Share screen (S)" / "Stop sharing (S)"; stopping
from the browser bar resets state. Picker cancel → nothing; other error → "Screen sharing didn't start. Try again."
No `getDisplayMedia` → disabled, title "Screen sharing isn't available on this device". Frames sent only on change.

| Event | Copy | Actions |
|---|---|---|
| Socket closes unexpectedly | "Connection lost. Everything up to now is saved." | **View transcripts** |
| Server `error` frame | "The interview hit a problem and had to stop. Everything up to now is saved." (never raw error) | **View transcripts**, **Back to setup** |
| Mic track ends | "Your microphone disconnected. Reconnect it, then press M to unmute." | — |

No auto-reconnect in this slice.

### 1d. Ending
- Confirm (`ConfirmationModal`): title "End the interview?", message "{Name} will stop here and your transcript will be
  saved. You can get feedback on it afterwards.", confirm "End interview", cancel "Keep going" (initial focus).
- After confirm: controls disabled, orb dimmed, "Wrapping up… saving your transcript"; send `session_ended` + reason,
  close WS, stop mic/share, navigate to `/transcripts`.
- `beforeunload` guard while live. `App.tsx` header nav: while live, clicking a nav link opens the same end confirm
  (or nav is hidden) — never silently kills the session.

## 2. Accessibility & keyboard
- One visually-hidden `aria-live="polite"` region: "Now in phase 4 of 7: Implementation.", "10 minutes left",
  "3 minutes left", "1 minute left", "Time's up.", "Screen sharing stopped." Visible timer `aria-hidden="true"`.
- Shortcuts (live only): **M** mute, **S** share, **E** end confirm. Ignore in inputs/textarea, with Ctrl/Meta/Alt,
  or when the modal is open. Esc closes modal.
- Modal: `role="dialog"`, `aria-modal`, `aria-labelledby`, focus trap, Esc, focus returns to End.
- Icon buttons keep `aria-label`; mute uses `aria-pressed`. Track cards + length = radiogroup with arrow keys.
- Focus ring `2px solid #3b82f6`, `outline-offset: 2px`. `prefers-reduced-motion` stops orb/ring animation.
- Contrast ≥4.5:1 on both backgrounds.

## 3. Tokens (no new colors)
| Use | Dark | Light |
|---|---|---|
| Page bg | `#0a0a0a` | `gray-50` |
| Card | `#111`, border `gray-800` | white, border `gray-200` |
| Glass pill | `rgba(255,255,255,.04)` border `.08` | `rgba(0,0,0,.03)` border `.08` |
| Listening/selected | `#60a5fa`/`#2563eb` | `#3b82f6`/`#1d4ed8` |
| Speaking | `#a78bfa`/`#7c3aed` | `#8b5cf6`/`#6d28d9` |
| Danger | `#f87171` | `#dc2626`, fill `#ef4444` |
Selected card: border `1.5px rgba(59,130,246,.6)`, bg `rgba(59,130,246,.08)`. Radii: 8px timer/preview/cards,
12px buttons, 24px modal, 999px pills/bar/End. Spacing 2rem (1.5rem ≤640px), 1.25rem between controls.
Labels 0.7–0.8rem uppercase 0.08–0.12em; name 0.95rem/600; timer monospace. Motion 0.2–0.4s ease.

## 4. Sign-off checks (@arlo-3414 will run)
1. Page load opens no socket and no mic prompt.
2. Setup cards from `/agents/interview-options`; a 3rd server track appears with no frontend change.
3. Phase minutes update with length; last choice persists across reload.
4. Loading / failed / no-tracks states + Try again.
5. Mic denied message; allow + Try again recovers without reload.
6. WS URL has `interview_type` + `duration_minutes`; 1008 → setup + message.
7. Connecting state + Cancel; 15 s timeout banner.
8. Timer from `session_clock` (`elapsed_seconds`); no `time_warning`/`time_context` sent; tones at 10/3 min.
9. Phase text + current segment change on frame; widths ∝ shares.
10. Badge ring + status for speaking/listening/muted.
11. End works in connecting (Cancel) and live (modal); "Keep going" focused; Esc closes.
12. M/S/E work, ignored in inputs/with modifiers, listed in titles.
13. Screen reader: phase change + 10/3/1-min marks announced once; timer not read every second.
14. Sharing badge; browser-bar stop resets; mobile share disabled with reason.
15. 390px: no overlap/horizontal scroll in setup/connecting/live; dark + light correct.
16. Reduced motion stops orb; focus rings visible.
17. `error` frame and dropped socket show their banners; raw error never shown.
18. `npm run build` green; no console errors during a 2-min session.
