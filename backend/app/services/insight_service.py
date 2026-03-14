import json
from google.adk.agents import SequentialAgent, ParallelAgent, LlmAgent
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from app.logger import logger

session_service = InMemorySessionService()

from app.prompts import (
    CONFIDENCE_AGENT_PROMPT,
    RADAR_AGENT_PROMPT,
    MARKET_GAP_AGENT_PROMPT,
    REPORT_COMPILER_PROMPT
)

# Define Agents
confidence_agent = LlmAgent(
    name="ConfidenceMapAgent",
    model="gemini-2.5-pro",
    instruction=CONFIDENCE_AGENT_PROMPT,
    output_key="confidence_data"
)

radar_agent = LlmAgent(
    name="ConceptRadarAgent",
    model="gemini-2.5-flash",
    instruction=RADAR_AGENT_PROMPT,
    output_key="radar_data"
)

market_gap_agent = LlmAgent(
    name="MarketGapAgent",
    model="gemini-2.5-pro",
    instruction=MARKET_GAP_AGENT_PROMPT,
    output_key="market_gap_data"
)

report_agent = LlmAgent(
    name="ReportCompilerAgent",
    model="gemini-2.5-flash",
    instruction=REPORT_COMPILER_PROMPT,
    output_key="final_report"
)

# Pipeline Definition
parallel_insight_agents = ParallelAgent(
    name="ParallelInsightAgents",
    sub_agents=[confidence_agent, radar_agent]
)

insights_pipeline = SequentialAgent(
    name="InsightsPipeline",
    sub_agents=[
        parallel_insight_agents, 
        market_gap_agent, 
        report_agent
    ]
)

def _parse_json_result(data_str: str) -> dict | None:
    if not data_str:
        return None
    try:
        # Strip potential markdown fences if model disobeys prompt
        clean_str = data_str.strip()
        if clean_str.startswith("```json"):
            clean_str = clean_str[7:]
        elif clean_str.startswith("```"):
            clean_str = clean_str[3:]
        if clean_str.endswith("```"):
            clean_str = clean_str[:-3]
        return json.loads(clean_str)
    except Exception as e:
        logger.error(f"Failed to parse JSON result: {e} | Data: {data_str[:100]}...")
        return None

async def run_insights_pipeline(user_id: str, session_id: str, candidate_profile: dict, raw_transcript: list[dict]):
    """
    Runs the full insight generation pipeline and returns the structured data and report text.
    """
    # Create offline session for insights mapping keys appropriately
    session = await session_service.create_session(
        app_name="prepguardian_insights",
        user_id=user_id,
        session_id=session_id + "_insights",
        state={
            "candidate_profile": json.dumps(candidate_profile),
            # Add target levels extracted correctly for prompt
            "target_role": candidate_profile.get("target_role", "Software Engineer"),
            "target_company": candidate_profile.get("target_company", "Top Tech Company"),
            "target_level": candidate_profile.get("target_level", "Mid-level"),
            "session_date": candidate_profile.get("session_date", ""),
            "candidate_name": candidate_profile.get("name", "Candidate"),
            "raw_transcript": json.dumps(raw_transcript)
        }
    )
    
    try:
        from google.adk.runners import Runner
        runner = Runner(
            app_name="prepguardian_insights",
            agent=insights_pipeline,
            session_service=session_service,
        )
        events = runner.run_async(user_id=user_id, session_id=session.id)
        async for _ in events:
            pass
        logger.info(f"Completed insight pipeline for session {session_id}")
    except Exception as e:
        logger.error(f"Insight pipeline failed for session {session_id}: {e}")
        return None

    conf_data = _parse_json_result(session.state.get("confidence_data"))
    radar_data = _parse_json_result(session.state.get("radar_data"))
    market_data = _parse_json_result(session.state.get("market_gap_data"))
    
    report_text = session.state.get("final_report", "").strip()
    # Strip fences from report text if present
    if report_text.startswith("```markdown"):
        report_text = report_text[11:]
    elif report_text.startswith("```"):
        report_text = report_text[3:]
    if report_text.endswith("```"):
        report_text = report_text[:-3]

    return {
        "confidence_data": conf_data,
        "radar_data": radar_data,
        "market_gap_data": market_data,
        "report_text": report_text.strip()
    }
