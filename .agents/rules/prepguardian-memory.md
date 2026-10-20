---
trigger: always_on
description: PrepGuardian memory pointer — load repo context before any code change
---

# PrepGuardian memory

Before touching code, read in order:

1. `AGENTS.md` — what the app is, contracts, landmines, working rules.
2. `docs/ARCHITECTURE.md` — full backend/frontend/ADK/insights reference with file:line numbers.
3. `docs/plans/00-OVERVIEW.md` — then the ONE plan file you were asked to implement
   (`01` prompts/caching/persona, `02` HelloInterview insights, `03` UX, `04` ADK/live refactor).

Do not re-derive architecture from scratch — it is already mapped. Update `AGENTS.md` /
`docs/ARCHITECTURE.md` when you change a contract (transcript shape, state keys, models, routes).
