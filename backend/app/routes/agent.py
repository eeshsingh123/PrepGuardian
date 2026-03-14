import json

from fastapi import APIRouter, WebSocket

from app.logger import logger
from app.services.agent_service import run_bidirectional_session


router = APIRouter(prefix="/agents", tags=["Agents"])


@router.websocket("/ws/{user_id}/{session_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str, session_id: str):
    """
    WebSocket endpoint for bidirectional audio communication with the ADK Agent.
    Accepts the connection, starts a live agent session, and runs the send/receive
    loops until either side disconnects.

    Args:
        websocket: The incoming WebSocket connection managed by FastAPI.
        user_id: Backend-generated user ID from authentication.
        session_id: Frontend-generated unique session identifier.
    """
    await websocket.accept()
    logger.info(f"Client {user_id} connected (session: {session_id}).")

    # If session startup fails (e.g. Gemini API unreachable), notify the client
    # and close the socket gracefully instead of leaving it hanging.
    try:
        await run_bidirectional_session(websocket, user_id, session_id)
    except Exception as e:
        logger.error(f"Failed to start agent session for {user_id}: {e}")
        await websocket.send_text(json.dumps({"error": str(e)}))
        await websocket.close(code=1011, reason="Agent session failed to start")
