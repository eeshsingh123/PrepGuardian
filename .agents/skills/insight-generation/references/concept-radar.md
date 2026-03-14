# Concept Radar — Reference

Agent that scores the candidate across 8 system design pillars.
Output renders as a radar/spider chart with a market bar overlay.

---

## Agent Definition

```python
radar_agent = LlmAgent(
    name="ConceptRadarAgent",
    model="gemini-3-flash-preview",
    instruction=RADAR_AGENT_PROMPT,
    output_key="radar_data"
)
```

> Flash is sufficient — this is structured extraction. The rubric is explicit and the
> transcript is the sole source of truth.

---

## Prompt

```python
RADAR_AGENT_PROMPT = """
You are a system design interview evaluator analyzing a transcript for concept coverage.

Evaluate the candidate across these 8 pillars. Assign a score 0 to 10 for each.

Pillar definitions:

1. Scalability
   Load balancing, horizontal scaling, sharding, traffic distribution, bottleneck identification.

2. Storage Design
   SQL vs NoSQL choice with justification, schema design, indexing, partitioning strategies.

3. Caching
   Cache layers, eviction policies (LRU, LFU), TTL, CDN usage, where caching fits and why.

4. API Design
   REST/gRPC/GraphQL with justification, idempotency, versioning, rate limiting, API gateway.

5. Reliability and Fault Tolerance
   Failure modes, retries, circuit breakers, replication, redundancy, SLAs, disaster recovery.

6. Observability
   Logging, metrics, distributed tracing, alerting, monitoring dashboards.

7. Async and Queuing
   Message queues, event-driven patterns, background workers, Kafka, SQS, pub/sub.

8. Security and Edge Cases
   Auth, authorization, rate limiting for abuse, duplicate requests, data races, cascading failures.

Scoring guide:
- 0: Never mentioned
- 1-3: Briefly touched, no substance
- 4-6: Surface level with some justification
- 7-9: Depth, trade-offs discussed, well-integrated into the design
- 10: Exceptional depth, proactively raised and fully resolved

Return ONLY valid JSON. No preamble, no markdown code fences.

{
  "pillars": {
    "Scalability": 8,
    "Storage Design": 5,
    "Caching": 3,
    "API Design": 7,
    "Reliability and Fault Tolerance": 2,
    "Observability": 0,
    "Async and Queuing": 6,
    "Security and Edge Cases": 4
  },
  "strongest": "Scalability",
  "weakest": "Observability",
  "avoided": ["Observability", "Reliability and Fault Tolerance"]
}

Transcript:
{raw_transcript}
"""
```

---

## Output Schema

```json
{
  "pillars": {
    "Scalability": 8,
    "Storage Design": 5,
    "Caching": 3,
    "API Design": 7,
    "Reliability and Fault Tolerance": 2,
    "Observability": 0,
    "Async and Queuing": 6,
    "Security and Edge Cases": 4
  },
  "strongest": "Scalability",
  "weakest": "Observability",
  "avoided": ["Observability", "Reliability and Fault Tolerance"]
}
```

---

## Chart Spec

**Type:** Radar/spider chart — Recharts `RadarChart` or Chart.js Radar
**Axes:** One per pillar (8 total)

- Two overlapping polygons:
  1. Candidate scores — filled, semi-transparent blue
  2. Market bar for their level — dashed orange outline, no fill
     - Mid-level → all pillars at 5 · Senior → 7 · Staff+ → 8
- Gap between polygons coloured amber/red wherever candidate falls below market bar
- `avoided` pillars called out in a warning box below the chart
- `strongest` shown as a green badge · `weakest` as a red badge
