from fastapi import APIRouter, HTTPException

from app.models import ConversationResponse, ConversationSummaryResponse
from app.services.conversation_service import (
    get_conversations_by_user,
    get_conversation_by_session,
    update_conversation_insights,
)
from app.constants import AppConstants
from app.services.user_service import get_user
from app.services.insight_service import run_insights_pipeline


router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get("/", response_model=list[ConversationSummaryResponse])
async def list_conversations(user_id: str):
    """
    Returns all conversation summaries for a user, sorted newest first.
    Each summary includes a short preview from the first agent response.
    """
    return await get_conversations_by_user(user_id)


@router.get("/{session_id}", response_model=ConversationResponse)
async def get_conversation(session_id: str):
    conversation = await get_conversation_by_session(session_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


@router.post("/{session_id}/generate-insights")
async def generate_insights(session_id: str, user_id: str):
    """
    Loads the conversation from the DB, runs the insight pipeline, and updates
    the conversation document with the new insights. Returns 200 + { "ok": true }
    on success; client should refetch the conversation.
    """
    conversation = await get_conversation_by_session(session_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    if conversation.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Not allowed to generate insights for this session.",
        )
    if not conversation.turns:
        raise HTTPException(
            status_code=400,
            detail="No transcript to analyze.",
        )
    user = await get_user(conversation.user_id)
    candidate_profile = {
        "name": user.name or "Candidate",
        "target_role": user.preferences or "Software Engineer",
        "target_company": user.target_company or AppConstants.DEFAULT_TARGET_COMPANY,
        "target_level": user.target_level or AppConstants.DEFAULT_TARGET_LEVEL,
        "years_experience": user.experience or "Not specified",
        "session_date": conversation.started_at.isoformat(),
    }
    raw_transcript = [t.model_dump(mode="json") for t in conversation.turns]
    insight_data = await run_insights_pipeline(
        user_id=conversation.user_id,
        session_id=session_id,
        candidate_profile=candidate_profile,
        raw_transcript=raw_transcript,
    )
    if insight_data is None:
        raise HTTPException(
            status_code=503,
            detail="Insight generation failed. Please try again.",
        )
    await update_conversation_insights(
        session_id,
        confidence_data=insight_data.get("confidence_data"),
        radar_data=insight_data.get("radar_data"),
        market_gap_data=insight_data.get("market_gap_data"),
        report_text=insight_data.get("report_text"),
    )
    return {"ok": True}
