import asyncio
import base64
import json
from collections.abc import AsyncGenerator

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from google.adk.agents import Agent, LiveRequestQueue
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.agents.run_config import RunConfig
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from google.genai.types import Blob, Content, Part
from motor.motor_asyncio import AsyncIOMotorDatabase

from app import prompts
from app.config import settings
from app.constants import AppConstants
from app.interview.tracks import get_track
from app.logger import logger
from app.schemas import UserPublic
from app.schemas.live import LiveSessionConfig
from app.services.conversation_service import ConversationTracker
from app.services.interview_session import (
    INTERVIEWER_NOTES_STATE_KEY,
    CueScheduler,
    InterviewClock,
    build_clock_state,
    candidate_context_from_state,
    get_interview_status,
    save_interview_note,
    session_config_from_state,
)
from app.services.live_session_service import LiveSessionService
from app.services.user_service import get_user


END_OF_SPEECH_SENSITIVITY = {
    "LOW": types.EndSensitivity.END_SENSITIVITY_LOW,
    "HIGH": types.EndSensitivity.END_SENSITIVITY_HIGH,
}


def build_agent_instruction(context: ReadonlyContext) -> str:
    """
    Builds the live interviewer instruction from the current session state.

    Args:
        context: ADK read-only context for the running live session.
    """
    config = session_config_from_state(context.state)
    candidate = candidate_context_from_state(context.state)
    track = get_track(config.interview_type)
    return prompts.build_live_instruction(track, candidate, config.duration_minutes)


root_agent = Agent(
    name=AppConstants.AGENT_NAME,
    model=settings.AGENT_LIVE_MODEL,
    description=prompts.AGENT_DESCRIPTION,
    instruction=build_agent_instruction,
    tools=[get_interview_status, save_interview_note],
)

session_service = InMemorySessionService()

runner = Runner(
    app_name=AppConstants.APP_NAME,
    agent=root_agent,
    session_service=session_service,
)


def build_candidate_state(user: UserPublic) -> dict[str, str]:
    """
    Builds the candidate profile stored in ADK session state. Unknown fields
    stay blank so the live prompt omits them instead of presenting them as facts.

    Args:
        user: Authenticated user profile.
    """
    return {
        "user_name": (user.name or "").strip(),
        "user_experience": (user.experience or "").strip(),
        "user_preferences": (user.preferences or "").strip(),
        "user_target_company": (user.target_company or "").strip(),
        "user_target_level": (user.target_level or "").strip(),
    }


def build_run_config() -> RunConfig:
    return RunConfig(
        response_modalities=AppConstants.RESPONSE_MODALITIES,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=settings.LIVE_VOICE,
                )
            )
        ),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                silence_duration_ms=settings.LIVE_VAD_SILENCE_DURATION_MS,
                end_of_speech_sensitivity=END_OF_SPEECH_SENSITIVITY[
                    settings.LIVE_VAD_END_OF_SPEECH_SENSITIVITY
                ],
                prefix_padding_ms=settings.LIVE_VAD_PREFIX_PADDING_MS,
            )
        ),
        context_window_compression=types.ContextWindowCompressionConfig(
            trigger_tokens=settings.LIVE_COMPRESSION_TRIGGER_TOKENS,
            sliding_window=types.SlidingWindow(
                target_tokens=settings.LIVE_COMPRESSION_TARGET_TOKENS,
            ),
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        session_resumption=types.SessionResumptionConfig(),
    )


async def start_agent_session(
    user_id: str,
    session_id: str,
    clock: InterviewClock,
    db: AsyncIOMotorDatabase,
) -> tuple[AsyncGenerator[Event, None], LiveRequestQueue]:
    """
    Creates or resumes the ADK session and starts a live bidirectional stream.

    Args:
        user_id: Backend-generated unique identifier for the user.
        session_id: Frontend-generated unique identifier for this session.
        clock: Server-owned clock started when the socket was accepted.
        db: MongoDB database used to load the candidate profile.

    Returns:
        The live event stream and request queue for this interview.
    """
    user = await get_user(user_id, db=db)
    candidate_state = build_candidate_state(user)
    clock_state = build_clock_state(clock)

    session = await runner.session_service.get_session(
        app_name=AppConstants.APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    if not session:
        await runner.session_service.create_session(
            app_name=AppConstants.APP_NAME,
            user_id=user_id,
            session_id=session_id,
            state={
                **candidate_state,
                **clock_state,
                INTERVIEWER_NOTES_STATE_KEY: [],
            },
        )
    else:
        await runner.session_service.append_event(
            session,
            Event(
                author="system",
                actions=EventActions(state_delta={**candidate_state, **clock_state}),
            ),
        )

    live_request_queue = LiveRequestQueue()
    live_events = runner.run_live(
        user_id=user_id,
        session_id=session_id,
        live_request_queue=live_request_queue,
        run_config=build_run_config(),
    )
    return live_events, live_request_queue


async def agent_to_client_messaging(
    websocket: WebSocket,
    live_events: AsyncGenerator[Event, None],
    tracker: ConversationTracker,
) -> None:
    """
    Forwards agent audio, text, transcripts, and usage data to the browser.

    Args:
        websocket: The active WebSocket connection to the client.
        live_events: Async generator of live events from the ADK runner.
        tracker: ConversationTracker that records transcript turns and usage.
    """
    current_agent_transcript: list[str] = []

    try:
        async for event in live_events:
            if event.output_transcription and event.output_transcription.text:
                transcript_text = event.output_transcription.text
                await websocket.send_text(
                    json.dumps(
                        {
                            "mime_type": "text/plain",
                            "data": transcript_text,
                            "is_transcript": True,
                        }
                    )
                )
                current_agent_transcript.append(transcript_text)

            if event.input_transcription and event.input_transcription.text:
                tracker.add_user_turn(event.input_transcription.text)

            if event.content and event.content.parts:
                for part in event.content.parts:
                    if (
                        part.inline_data
                        and part.inline_data.mime_type
                        and part.inline_data.mime_type.startswith("audio/pcm")
                        and part.inline_data.data
                    ):
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "mime_type": "audio/pcm",
                                    "data": base64.b64encode(
                                        part.inline_data.data
                                    ).decode("ascii"),
                                }
                            )
                        )

                    if part.text and event.partial:
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "mime_type": "text/plain",
                                    "data": part.text,
                                }
                            )
                        )

            if event.usage_metadata:
                tracker.record_usage(event.usage_metadata)

            if event.turn_complete or event.interrupted:
                if current_agent_transcript:
                    tracker.add_agent_turn(" ".join(current_agent_transcript))
                    current_agent_transcript = []
                if event.turn_complete:
                    tracker.record_model_turn()
                await websocket.send_text(
                    json.dumps(
                        {
                            "turn_complete": event.turn_complete,
                            "interrupted": event.interrupted,
                        }
                    )
                )

    except WebSocketDisconnect:
        logger.info("Client disconnected from agent_to_client_messaging")
    except Exception as e:
        logger.error(f"Error in agent_to_client_messaging: {e}")


async def client_to_agent_messaging(
    websocket: WebSocket,
    live_request_queue: LiveRequestQueue,
    tracker: ConversationTracker,
    live_session_service: LiveSessionService | None = None,
) -> None:
    """
    Forwards browser audio, screen frames, and text to the live agent.

    Args:
        websocket: The active WebSocket connection to the client.
        live_request_queue: The ADK queue used to send input to the running agent.
        tracker: ConversationTracker that records user transcript turns.
        live_session_service: Optional sticky-session refresher.
    """
    try:
        while True:
            message_json = await websocket.receive_text()
            if live_session_service is not None:
                await live_session_service.refresh_session(
                    tracker.user_id,
                    tracker.session_id,
                )
            message = json.loads(message_json)
            mime_type = message.get("mime_type")
            data = message.get("data")

            if mime_type == "application/session-control":
                if message.get("event") == "session_ended":
                    reason = message.get("reason")
                    tracker.mark_ended(reason if isinstance(reason, str) else None)
                    break
                continue

            if not isinstance(data, str):
                logger.warning(f"Missing payload for mime type: {mime_type}")
                continue

            if mime_type == "text/plain":
                live_request_queue.send_content(
                    content=Content(role="user", parts=[Part.from_text(text=data)])
                )
                tracker.add_user_turn(data)
                logger.info("[CLIENT TO AGENT]: Text input received.")
            elif isinstance(mime_type, str) and mime_type.startswith("audio/pcm"):
                live_request_queue.send_realtime(
                    Blob(
                        data=base64.b64decode(data),
                        mime_type="audio/pcm;rate=16000",
                    )
                )
            elif mime_type in ("image/jpeg", "image/png"):
                live_request_queue.send_realtime(
                    Blob(data=base64.b64decode(data), mime_type=mime_type)
                )
            else:
                logger.warning(f"Unrecognized mime type: {mime_type}")

    except WebSocketDisconnect:
        logger.info("Client disconnected from client_to_agent_messaging")
    except Exception as e:
        logger.error(f"Error in client_to_agent_messaging: {e}")


async def run_bidirectional_session(
    websocket: WebSocket,
    user_id: str,
    session_id: str,
    config: LiveSessionConfig,
    db: AsyncIOMotorDatabase,
    live_session_service: LiveSessionService | None = None,
) -> None:
    """
    Runs one live interview from accept until disconnect or session_ended.

    Args:
        websocket: The accepted WebSocket connection to the client.
        user_id: Backend-generated unique identifier for the connected user.
        session_id: Frontend-generated unique identifier for this session.
        config: Interview type and duration chosen by the candidate.
        db: MongoDB database used to persist the transcript.
        live_session_service: Optional sticky-session refresher.
    """
    clock = InterviewClock(config)
    live_events, live_request_queue = await start_agent_session(
        user_id,
        session_id,
        clock,
        db,
    )
    tracker = ConversationTracker(
        session_id,
        user_id,
        db,
        config,
        started_at=clock.started_at,
    )
    scheduler_task = asyncio.create_task(
        CueScheduler(clock, websocket, live_request_queue).run()
    )
    agent_task = asyncio.create_task(
        agent_to_client_messaging(websocket, live_events, tracker)
    )
    client_task = asyncio.create_task(
        client_to_agent_messaging(
            websocket,
            live_request_queue,
            tracker,
            live_session_service,
        )
    )

    try:
        done, pending = await asyncio.wait(
            [agent_task, client_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if exc:
                logger.error(f"Task error for client {user_id}: {exc}")
    finally:
        live_request_queue.close()
        scheduler_task.cancel()
        scheduler_result = await asyncio.gather(
            scheduler_task,
            return_exceptions=True,
        )
        for result in scheduler_result:
            if isinstance(result, Exception) and not isinstance(
                result, asyncio.CancelledError
            ):
                logger.error(f"Cue scheduler error for client {user_id}: {result}")

        session = await runner.session_service.get_session(
            app_name=AppConstants.APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        notes = (
            list(session.state.get(INTERVIEWER_NOTES_STATE_KEY) or [])
            if session
            else []
        )
        await tracker.save(interviewer_notes=notes)
