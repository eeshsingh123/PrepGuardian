---
name: insight-generation
description: >
  Use this skill whenever implementing, modifying, or debugging the PrepGuardian insights pipeline.
  Triggers when working on any of the three insight agents (confidence map, concept radar, market gap),
  the report compiler, pipeline wiring, session state, or the post-session analysis flow.
  Always read this file first, then load only the reference file(s) relevant to the task.
---

# Insight Generation Pipeline

Post-session analysis pipeline for PrepGuardian. Runs after a live interview session ends and
produces three structured insights plus an exportable markdown report.

## Models

| Use case | Model |
|---|---|
| Nuanced judgment | `gemini-3.1-pro-preview` |
| Straightforward extraction / formatting | `gemini-3-flash-preview` |

## Pipeline Shape

```
Parallel(ConfidenceMapAgent, ConceptRadarAgent) → MarketGapAgent → ReportCompilerAgent
```

- `ConfidenceMapAgent` and `ConceptRadarAgent` run in parallel — both only need `raw_transcript`
- `MarketGapAgent` runs after both complete — reads `confidence_data` + `radar_data`
- `ReportCompilerAgent` runs last — reads all three payloads

## Pipeline Assembly

```python
from google.adk.agents import SequentialAgent, ParallelAgent, LlmAgent

parallel_insight_agents = ParallelAgent(
    name="ParallelInsightAgents",
    sub_agents=[confidence_agent, radar_agent]
)

insights_pipeline = SequentialAgent(
    name="InsightsPipeline",
    sub_agents=[
        parallel_insight_agents,  # writes: confidence_data + radar_data
        market_gap_agent,         # writes: market_gap_data
        report_agent              # writes: final_report
    ]
)
```

## Session State Keys

| Key | Written by | Read by |
|---|---|---|
| `raw_transcript` | Pre-pipeline | ConfidenceMapAgent, ConceptRadarAgent |
| `candidate_profile` | Session onboarding | MarketGapAgent, ReportCompilerAgent |
| `confidence_data` | ConfidenceMapAgent | MarketGapAgent, ReportCompilerAgent |
| `radar_data` | ConceptRadarAgent | MarketGapAgent, ReportCompilerAgent |
| `market_gap_data` | MarketGapAgent | ReportCompilerAgent |
| `final_report` | ReportCompilerAgent | Artifact save, frontend |

`candidate_profile` shape:
```python
{
    "name": str,
    "target_role": str,       # e.g. "Senior Software Engineer"
    "target_company": str,    # e.g. "Google"
    "target_level": str,      # "Mid-level" | "Senior" | "Staff+"
    "years_experience": str,
    "session_date": str       # ISO date string
}
```

## Trigger Pattern

```python
async def run_insights_pipeline(session, candidate_profile: dict):
    session.state["candidate_profile"] = candidate_profile
    await insights_pipeline.run_async(session=session)

    report_text = session.state.get("final_report", "")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"session_report_{timestamp}.md"
    await session.artifacts.save(filename, report_text, mime_type="text/markdown")

    return {
        "confidence_data": session.state.get("confidence_data"),
        "radar_data": session.state.get("radar_data"),
        "market_gap_data": session.state.get("market_gap_data"),
        "report_artifact": filename
    }
```

## End-to-End Flow

```
1. Session ends → raw_transcript + candidate_profile written to session.state

2. Stage 1 — Parallel
   ├── ConfidenceMapAgent  → raw_transcript → confidence_data
   └── ConceptRadarAgent   → raw_transcript → radar_data

3. Stage 2 — Sequential
   └── MarketGapAgent → confidence_data + radar_data → market_gap_data

4. Stage 3 — Sequential
   └── ReportCompilerAgent → all three payloads → final_report

5. Artifact saved as session_report_{timestamp}.md

6. JSON payloads returned to frontend for chart rendering
```

---

## References

Load the relevant reference file for the task at hand. Do not load all of them at once.

| Task | Reference file |
|---|---|
| Confidence scoring agent — prompt, schema, chart spec | `references/confidence-map.md` |
| Concept radar agent — prompt, schema, chart spec | `references/concept-radar.md` |
| Market gap agent — prompt, level definitions, schema, chart spec | `references/market-gap.md` |
| Report compiler agent — prompt, markdown template, artifact save | `references/report-compiler.md` |
