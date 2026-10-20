import json
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from fastapi import WebSocketException
from fastapi import status
from fastapi.websockets import WebSocketDisconnect
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ValidationError

from app.constants import InterviewerConstants, RedisConstants
from app.dependencies import RedisDep
from app.interview.tracks import ALLOWED_DURATIONS_MINUTES, DEFAULT_DURATION_MINUTES, TRACKS
from app.logger import logger
from app.schemas import LiveSessionConfig
from app.schemas.users import UserPublic
from app.security import get_current_user
from app.services.agent_service import AgentUnavailableError, run_bidirectional_session
from app.services.live_session_service import LiveSessionService, LiveSessionTicket


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


class SessionStartResponse(BaseModel):
    session_id: str
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


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    response_model=SessionStartResponse,
)
async def create_session(
    config: LiveSessionConfig,
    current_user: Annotated[UserPublic, Depends(get_current_user)],
    redis: RedisDep,
) -> SessionStartResponse:
    service = LiveSessionService(redis)
    session_id = f"sess_{uuid4().hex}"
    if not await service.start_session(current_user.user_id, session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="active_session",
        )

    ticket = await service.issue_session_ticket(
        LiveSessionTicket(
            user_id=current_user.user_id,
            session_id=session_id,
            interview_type=config.interview_type,
            duration_minutes=config.duration_minutes,
        )
    )
    return SessionStartResponse(
        session_id=session_id,
        ticket=ticket,
        expires_in=RedisConstants.WS_TICKET_TTL_SECONDS,
    )


async def close_websocket(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except RuntimeError:
        return


async def send_error_and_close(websocket: WebSocket, error: str) -> None:
    try:
        await websocket.send_text(json.dumps({"error": error}))
    except (RuntimeError, WebSocketDisconnect):
        return
    await close_websocket(websocket, 1011)


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    ticket: str | None = None,
):
    """
    Accepts a live interview socket once its one-time ticket is valid.

    Args:
        websocket: The incoming WebSocket connection managed by FastAPI.
        ticket: One-time ticket issued by `POST /agents/sessions`.
    """
    if not ticket:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    redis = getattr(websocket.app.state, "redis", None)
    if redis is None:
        raise WebSocketException(code=status.WS_1011_INTERNAL_ERROR)

    db: AsyncIOMotorDatabase | None = getattr(websocket.app.state, "mongo_db", None)
    if db is None:
        raise WebSocketException(code=status.WS_1011_INTERNAL_ERROR)

    service = LiveSessionService(redis)
    session = await service.consume_session_ticket(ticket)
    if session is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    try:
        config = LiveSessionConfig(
            interview_type=session.interview_type,
            duration_minutes=session.duration_minutes,
        )
    except ValidationError as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION) from exc

    await service.refresh_session(session.user_id, session.session_id)
    await websocket.accept()
    logger.info(f"Client {session.user_id} connected (session: {session.session_id}).")

    try:
        await run_bidirectional_session(
            websocket,
            session.user_id,
            session.session_id,
            config,
            db,
            service,
        )
    except AgentUnavailableError as exc:
        logger.error(f"Agent unavailable for {session.user_id}: {exc}")
        await send_error_and_close(websocket, "agent_unavailable")
    except Exception as exc:
        logger.error(f"Live session failed for {session.user_id}: {exc}")
        await send_error_and_close(websocket, "internal")
    else:
        await close_websocket(websocket, 1000)
    finally:
        await service.remove_session(session.user_id, session.session_id)
