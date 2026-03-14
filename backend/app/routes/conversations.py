from fastapi import APIRouter, HTTPException

from app.models import ConversationResponse, ConversationSummaryResponse
from app.services.conversation_service import (
    get_conversations_by_user,
    get_conversation_by_session,
)

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
