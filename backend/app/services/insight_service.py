import json
from typing import Any

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai.types import Content, Part

from app.logger import logger
from app.prompts import (
    CONFIDENCE_AGENT_PROMPT,
    MARKET_GAP_AGENT_PROMPT,
    RADAR_AGENT_PROMPT,
    REPORT_COMPILER_PROMPT,
)
from app.schemas import CandidateProfile, ConfidenceData, MarketGapData, RadarData


session_service = InMemorySessionService()

# Define Agents
confidence_agent = LlmAgent(
    name="ConfidenceMapAgent",
    model="gemini-2.5-pro",
    instruction=CONFIDENCE_AGENT_PROMPT,
    output_schema=ConfidenceData,
    output_key="confidence_data"
)

radar_agent = LlmAgent(
    name="ConceptRadarAgent",
    model="gemini-2.5-flash",
    instruction=RADAR_AGENT_PROMPT,
    output_schema=RadarData,
    output_key="radar_data"
)

market_gap_agent = LlmAgent(
    name="MarketGapAgent",
    model="gemini-2.5-pro",
    instruction=MARKET_GAP_AGENT_PROMPT,
    output_schema=MarketGapData,
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
        report_agent,
    ]
)


def normalize_report_text(report_text: Any) -> str | None:
    if not isinstance(report_text, str):
        return None

    clean_report = report_text.strip()
    if clean_report.startswith("```markdown"):
        clean_report = clean_report[11:]
    elif clean_report.startswith("```"):
        clean_report = clean_report[3:]
    if clean_report.endswith("```"):
        clean_report = clean_report[:-3]

    clean_report = clean_report.strip()
    return clean_report or None


def get_state_dict_value(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


async def run_insights_pipeline(
    user_id: str,
    session_id: str,
    candidate_profile: dict[str, Any],
    raw_transcript: list[dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        profile = CandidateProfile.model_validate(candidate_profile)

        # Create an isolated offline session for the insight workflow.
        session = await session_service.create_session(
            app_name="prepguardian_insights",
            user_id=user_id,
            session_id=session_id + "_insights",
            state={
                "candidate_profile": profile.model_dump_json(),
                "target_role": profile.target_role,
                "target_company": profile.target_company,
                "target_level": profile.target_level,
                "session_date": profile.session_date,
                "candidate_name": profile.name,
                "raw_transcript": json.dumps(raw_transcript, default=str),
            }
        )

        runner = Runner(
            app_name="prepguardian_insights",
            agent=insights_pipeline,
            session_service=session_service,
        )
        new_message = Content(
            role="user",
            parts=[Part.from_text(text="Generate insights from the session transcript and candidate profile in state.")],
        )
        events = runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=new_message,
        )
        async for _ in events:
            pass
        logger.info(f"Completed insight pipeline for session {session_id}")

        refreshed_session = await session_service.get_session(
            app_name="prepguardian_insights",
            user_id=user_id,
            session_id=session.id,
        )
        if not refreshed_session:
            logger.error(
                "Insight session '%s' could not be reloaded after pipeline execution.",
                session.id,
            )
            return None

        confidence_data = get_state_dict_value(refreshed_session.state.get("confidence_data"))
        radar_data = get_state_dict_value(refreshed_session.state.get("radar_data"))
        market_gap_data = get_state_dict_value(refreshed_session.state.get("market_gap_data"))
        report_text = normalize_report_text(refreshed_session.state.get("final_report"))

        outputs = {
            "confidence_data": confidence_data,
            "radar_data": radar_data,
            "market_gap_data": market_gap_data,
            "report_text": report_text,
        }
        present_keys = [key for key, value in outputs.items() if value is not None]
        missing_keys = [key for key, value in outputs.items() if value is None]

        logger.info(
            "Insight session '%s' refreshed with outputs present=%s missing=%s",
            session.id,
            present_keys,
            missing_keys,
        )

        if not present_keys:
            return None

        return outputs
    except Exception as exc:
        logger.exception(
            "Insight pipeline failed for session '%s': %s",
            session_id,
            exc,
        )
        return None
