# Confidence Map — Reference

Agent that scores candidate confidence turn-by-turn from the transcript.
Output renders as a line chart showing trajectory, peak, and drop moments.

---

## Agent Definition

```python
confidence_agent = LlmAgent(
    name="ConfidenceMapAgent",
    model="gemini-3.1-pro-preview",
    instruction=CONFIDENCE_AGENT_PROMPT,
    output_key="confidence_data"
)
```

---

## Prompt

```python
CONFIDENCE_AGENT_PROMPT = """
You are an expert interview evaluator analyzing a system design interview transcript.

You will receive a structured transcript as a JSON array of turns. Each turn has:
- turn (index number)
- role ("agent" or "candidate")
- type ("question", "response", "hint", "redirect")
- text (what was said)

Your task: for each CANDIDATE turn, assign a confidence score from 0 to 10.

Scoring rubric:
- 9-10: Structured, complete, proactive. Candidate drives the answer with clear frameworks.
- 7-8: Good answer, minor gaps, minimal prompting needed.
- 5-6: Adequate but shallow. Required some leading from the agent.
- 3-4: Struggled noticeably. Vague, unstructured, or heavily reliant on hints.
- 1-2: Could not answer without significant intervention.
- 0: No meaningful response or off-topic entirely.

Signals to use when scoring:
- Structural clarity: Did they open with requirements, constraints, scale before jumping to solution?
- Completeness: Did they address the question fully without being redirected?
- Hedge language: Count uses of "I think", "maybe", "not sure", "probably", "I guess"
- Recovery: If the prior agent turn was a hint or redirect, did they recover well?
- Depth indicators: Did they mention trade-offs, justify decisions, raise failure scenarios?

Also identify:
- peak_turn: candidate turn index where confidence was highest
- drop_turn: candidate turn index where confidence dropped the most
- trend: overall trajectory — "improving", "declining", "stable", or "volatile"
- average_score: mean across all scored turns, rounded to 1 decimal

Return ONLY valid JSON. No preamble, no explanation, no markdown code fences.

{
  "scores": [
    {"turn": 2, "score": 7, "note": "clear opening, defined requirements cleanly"},
    {"turn": 4, "score": 5, "note": "went vague on storage layer, needed hint"}
  ],
  "peak_turn": 6,
  "drop_turn": 10,
  "average_score": 6.1,
  "trend": "declining"
}

Transcript:
{raw_transcript}
"""
```

---

## Output Schema

```json
{
  "scores": [
    { "turn": 2, "score": 7, "note": "string" }
  ],
  "peak_turn": 6,
  "drop_turn": 10,
  "average_score": 6.1,
  "trend": "declining | improving | stable | volatile"
}
```

---

## Chart Spec

**Type:** Line chart — Recharts `LineChart` or Chart.js Line
**X axis:** Turn number · **Y axis:** Score 0–10

- Dot at each data point; show `note` as tooltip on hover
- `peak_turn` → green filled circle, labelled "Peak"
- `drop_turn` → red filled circle, labelled "Drop"
- Horizontal dashed reference line at market bar for candidate's level:
  - Mid-level → 5.5 · Senior → 7.0 · Staff+ → 8.5
- Area under line: green where score is at or above reference line, red where below
- Display `average_score` and `trend` as badges in the chart header
