import json

from fastapi import APIRouter, WebSocket
from fastapi import WebSocketException
from fastapi import status

from app.db.mongo import get_mongo_db
from app.logger import logger
from app.security import get_websocket_user
from app.services.agent_service import run_bidirectional_session
from app.services.live_session_service import LiveSessionService


router = APIRouter(prefix="/agents", tags=["Agents"])


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str, token: str | None = None):
    """
    WebSocket endpoint for bidirectional audio communication with the ADK Agent.
    Accepts the connection, starts a live agent session, and runs the send/receive
    loops until either side disconnects.

    Args:
        websocket: The incoming WebSocket connection managed by FastAPI.
        session_id: Frontend-generated unique session identifier.
    """
    redis = getattr(websocket.app.state, "redis", None)
    if redis is None:
        raise WebSocketException(code=status.WS_1011_INTERNAL_ERROR)

    user = await get_websocket_user(token, get_mongo_db(), redis)
    live_session_service = LiveSessionService(redis)
    registered = await live_session_service.register_session(user.user_id, session_id)
    if not registered:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    await websocket.accept()
    logger.info(f"Client {user.user_id} connected (session: {session_id}).")

    # If session startup fails (e.g. Gemini API unreachable), notify the client
    # and close the socket gracefully instead of leaving it hanging.
    try:
        await run_bidirectional_session(
            websocket,
            user.user_id,
            session_id,
            live_session_service,
        )
    except Exception as e:
        logger.error(f"Failed to start agent session for {user.user_id}: {e}")
        await websocket.send_text(json.dumps({"error": str(e)}))
        await websocket.close(code=1011, reason="Agent session failed to start")
    finally:
        await live_session_service.remove_session(user.user_id, session_id)
