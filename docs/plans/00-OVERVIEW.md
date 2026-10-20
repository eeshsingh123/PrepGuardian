# Plans Overview — read this before picking up work

> Each plan below is self-contained: an agent can implement it end-to-end
> (backend + frontend + tests) using only the linked plan + `AGENTS.md` + `docs/ARCHITECTURE.md`.
> Do them in numeric order; dependencies noted per plan.

## Plan index

| File | Goal | Depends on | Rough size |
|---|---|---|---|
| `01-prompts-caching-interviewer-persona.md` | Split the 190-line mega-prompt into cacheable static prefix + dynamic suffix; fix model strings; make the interviewer sound human; correct caching expectations (Live = NO cache, insights = cache) | none (do first — 02/04 reuse its prompt layout) | M |
| `02-insights-hellointerview-framework.md` | Replace generic insights with HelloInterview LLD 5-stage scored rubric: per-section score + evidence + drills, visual stepper + analytical charts + report v2 | 01 (needs fixed transcript contract + prompt layout) | L |
| `03-ux-redesign.md` | Lobby → live (captions, turns, timer, whiteboard) → debrief (stepper, evidence, drills); AudioWorklet; component splits; engaging visual design | 01 for persona copy, 02 for framework charts (can start in parallel with mocks) | L |
| `04-live-api-adk-refactor.md` | Decide ADK vs alternatives (verdict: **keep ADK**), migrate to `gemini-3.8-live`, fix P0 bugs, persistent sessions, VAD/speech config, error/observability cleanup | 01 (prompt split) — implement P0 fixes alongside 01 if urgent | M |

## Recommended order

1. **01 first** — unblocks everything (prompt files move, model strings change).
2. **04 P0 fixes** alongside 01 (5 small bug fixes, same files).
3. **02 next** — backend-heavy, defines `framework_data` contract frontend needs.
4. **03 last** — consumes 01 copy + 02 charts; can scaffold with mock data earlier.

## Global acceptance (all plans)

- `cd backend && uv run pytest` green; `cd frontend && npm run build` green.
- No hardcoded model strings outside `backend/app/constants.py` (env-overridable).
- No `.env` secrets committed; `docs/ARCHITECTURE.md §8` debt row(s) for the plan struck or updated.
- Every async UI op has loading / error / empty states; no silent failures.
- Ask when ambiguous; never commit/push unless asked.

## GitHub context

Remote `https://github.com/eeshsingh123/PrepGuardian.git`, HEAD `6af7ec6 Timer context…`
on `feat/ux-timer-integration` (dirty). Base new work off HEAD; keep PRs per-plan.
