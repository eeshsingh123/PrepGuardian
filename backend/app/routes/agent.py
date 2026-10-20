import json
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket
from fastapi import WebSocketException
from fastapi import status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ValidationError

from app.constants import InterviewerConstants, RedisConstants
from app.dependencies import RedisDep
from app.interview.tracks import ALLOWED_DURATIONS_MINUTES, DEFAULT_DURATION_MINUTES, TRACKS
from app.logger import logger
from app.schemas import LiveSessionConfig
from app.schemas.users import UserPublic
from app.security import get_current_user
from app.services.agent_service import run_bidirectional_session
from app.services.live_session_service import LiveSessionService


router = APIRouter(prefix="/agents", tags=["Agents"])


class PhaseOption(BaseModel):
    key: str
    title: str
    share: float
    goal: str


class TrackOption(BaseModel):
    type: str
    title: str
    phases: list[PhaseOption]


class InterviewOptionsResponse(BaseModel):
    interviewer_name: str
    durations_minutes: list[int]
    default_duration_minutes: int
    tracks: list[TrackOption]


class WsTicketResponse(BaseModel):
    ticket: str
    expires_in: int


@router.get("/interview-options", response_model=InterviewOptionsResponse)
async def interview_options(
    current_user: UserPublic = Depends(get_current_user),
) -> InterviewOptionsResponse:
    return InterviewOptionsResponse(
        interviewer_name=InterviewerConstants.NAME,
        durations_minutes=list(ALLOWED_DURATIONS_MINUTES),
        default_duration_minutes=DEFAULT_DURATION_MINUTES,
        tracks=[
            TrackOption(
                type=track.type.value,
                title=track.title,
                phases=[
                    PhaseOption(
                        key=phase.key,
                        title=phase.title,
                        share=phase.share,
                        goal=phase.goal,
                    )
                    for phase in track.phases
                ],
            )
            for track in TRACKS.values()
        ],
    )


@router.post("/ws-ticket", response_model=WsTicketResponse)
async def websocket_ticket(
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    redis: RedisDep,
) -> WsTicketResponse:
    ticket = await LiveSessionService(redis).issue_ws_ticket(current_user.user_id)
    return WsTicketResponse(
        ticket=ticket,
        expires_in=RedisConstants.WS_TICKET_TTL_SECONDS,
    )


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    ticket: str | None = None,
    interview_type: str | None = None,
    duration_minutes: int | None = None,
):
    """
    Accepts a live interview socket once the config and one-time ticket are valid.

    Args:
        websocket: The incoming WebSocket connection managed by FastAPI.
        session_id: Frontend-generated unique session identifier.
        ticket: One-time ticket issued by `POST /agents/ws-ticket`.
        interview_type: Interview track key (`lld` or `hld`).
        duration_minutes: Interview length in minutes.
    """
    config_values: dict[str, object] = {}
    if interview_type is not None:
        config_values["interview_type"] = interview_type
    if duration_minutes is not None:
        config_values["duration_minutes"] = duration_minutes

    try:
        config = LiveSessionConfig(**config_values)
    except ValidationError as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION) from exc

    if not ticket:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    redis = getattr(websocket.app.state, "redis", None)
    if redis is None:
        raise WebSocketException(code=status.WS_1011_INTERNAL_ERROR)

    db: AsyncIOMotorDatabase | None = getattr(websocket.app.state, "mongo_db", None)
    if db is None:
        raise WebSocketException(code=status.WS_1011_INTERNAL_ERROR)

    live_session_service = LiveSessionService(redis)
    user_id = await live_session_service.consume_ws_ticket(ticket)
    if user_id is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    registered = await live_session_service.register_session(user_id, session_id)
    if not registered:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    await websocket.accept()
    logger.info(f"Client {user_id} connected (session: {session_id}).")

    # If session startup fails (e.g. Gemini API unreachable), notify the client
    # and close the socket gracefully instead of leaving it hanging.
    try:
        await run_bidirectional_session(
            websocket,
            user_id,
            session_id,
            config,
            db,
            live_session_service,
        )
    except Exception as e:
        logger.error(f"Failed to start agent session for {user_id}: {e}")
        await websocket.send_text(json.dumps({"error": str(e)}))
        await websocket.close(code=1011, reason="Agent session failed to start")
    finally:
        await live_session_service.remove_session(user_id, session_id)
