import json
import base64
import asyncio

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

from motor.motor_asyncio import AsyncIOMotorDatabase

from google.genai import types
from google.genai.types import Part, Content, Blob
from google.adk.runners import Runner
from google.adk.agents import Agent, LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools import google_search
from google.adk.events import Event, EventActions

from app.constants import AppConstants, ModelConstants
from app.logger import logger
from app.prompts import AGENT_DESCRIPTION, AGENT_INSTRUCTION
from app.services.user_service import get_user
from app.services.conversation_service import ConversationTracker
from app.services.live_session_service import LiveSessionService

root_agent = Agent(
    name=AppConstants.AGENT_NAME,
    model=ModelConstants.AGENT_LIVE_MODEL,
    description=AGENT_DESCRIPTION,
    instruction=AGENT_INSTRUCTION,
    tools=[google_search],
)

session_service = InMemorySessionService()

runner = Runner(
    app_name=AppConstants.APP_NAME,
    agent=root_agent,
    session_service=session_service,
)


async def start_agent_session(user_id: str, session_id: str, db: AsyncIOMotorDatabase):
    """
    Creates or retrieves an existing session for the given user and starts a live
    bidirectional streaming session with the ADK runner.

    Args:
        user_id: Backend-generated unique identifier for the user.
        session_id: Frontend-generated unique identifier for this session.

    Returns:
        A tuple of (live_events async generator, LiveRequestQueue) for the session.
    """
    # Fetch user data to inject into session context for prompt instructions
    user = await get_user(user_id, db=db)
    user_state = {
        "user_name": user.name or "Not specified",
        "user_experience": user.experience or "Not specified",
        "user_preferences": user.preferences or "Not specified",
        "user_target_company": user.target_company or AppConstants.DEFAULT_TARGET_COMPANY,
        "user_target_level": user.target_level or AppConstants.DEFAULT_TARGET_LEVEL,
    }

    session = await runner.session_service.get_session(
        app_name=AppConstants.APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    if not session:
        session = await runner.session_service.create_session(
            app_name=AppConstants.APP_NAME,
            user_id=user_id,
            session_id=session_id,
            state=user_state
        )
    else:
        # Update existing session state via append_event
        await runner.session_service.append_event(
            session,
            Event(
                author="system",
                actions=EventActions(state_delta=user_state)
            )
        )

    run_config = RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=AppConstants.RESPONSE_MODALITIES,
        session_resumption=types.SessionResumptionConfig(),
        # Enables context window compression to remove the 10-minute Vertex AI
        # session duration limit and prevent token exhaustion on long calls.
        context_window_compression=types.ContextWindowCompressionConfig(
            trigger_tokens=100000,
            sliding_window=types.SlidingWindow(target_tokens=80000),
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    live_request_queue = LiveRequestQueue()

    live_events = runner.run_live(
        user_id=user_id,
        session_id=session.id,
        live_request_queue=live_request_queue,
        run_config=run_config,
    )
    return live_events, live_request_queue


async def agent_to_client_messaging(
    websocket: WebSocket, live_events, tracker: ConversationTracker
):
    """
    Continuously reads events from the agent's live event stream and forwards
    them to the connected WebSocket client. Handles audio PCM chunks, partial
    text responses, audio transcripts, and turn-completion signals. Also records
    agent transcript turns into the ConversationTracker.

    Args:
        websocket: The active WebSocket connection to the client.
        live_events: Async generator of LiveEvent objects from the ADK runner.
        tracker: ConversationTracker instance to record agent turns.
    """
    current_agent_transcript = []
    
    try:
        async for event in live_events:
            # Agent's spoken words transcribed back to text
            if event.output_transcription and event.output_transcription.text:
                transcript_text = event.output_transcription.text
                message = {
                    "mime_type": "text/plain",
                    "data": transcript_text,
                    "is_transcript": True,
                }
                await websocket.send_text(json.dumps(message))
                current_agent_transcript.append(transcript_text)

            # User's audio input transcribed to text by Gemini
            if event.input_transcription and event.input_transcription.text:
                tracker.add_user_turn(event.input_transcription.text)

            part: Part = (
                event.content and event.content.parts and event.content.parts[0]
            )
            if part:
                is_audio = (
                    part.inline_data
                    and part.inline_data.mime_type.startswith("audio/pcm")
                )
                if is_audio:
                    audio_data = part.inline_data and part.inline_data.data
                    if audio_data:
                        message = {
                            "mime_type": "audio/pcm",
                            "data": base64.b64encode(audio_data).decode("ascii"),
                        }
                        await websocket.send_text(json.dumps(message))

                if part.text and event.partial:
                    message = {
                        "mime_type": "text/plain",
                        "data": part.text,
                    }
                    await websocket.send_text(json.dumps(message))

            if event.turn_complete or event.interrupted:
                if current_agent_transcript:
                    full_turn_text = " ".join(current_agent_transcript)
                    tracker.add_agent_turn(full_turn_text)
                    current_agent_transcript = []

                message = {
                    "turn_complete": event.turn_complete,
                    "interrupted": event.interrupted,
                }
                await websocket.send_text(json.dumps(message))

    except WebSocketDisconnect:
        logger.info("Client disconnected from agent_to_client_messaging")
    except Exception as e:
        logger.error(f"Error in agent_to_client_messaging: {e}")


async def client_to_agent_messaging(
    websocket: WebSocket,
    live_request_queue: LiveRequestQueue,
    tracker: ConversationTracker,
    live_session_service: LiveSessionService | None = None,
):
    """
    Continuously reads incoming WebSocket messages from the client and forwards
    them to the agent's LiveRequestQueue. Supports plain text (turn-by-turn),
    real-time audio PCM, and image blobs (JPEG/PNG). Records text-based user
    turns into the ConversationTracker.

    Args:
        websocket: The active WebSocket connection to the client.
        live_request_queue: The ADK queue used to send input to the running agent.
        tracker: ConversationTracker instance to record user text turns.
    """
    last_time_context_sent_at = 0.0
    last_time_context_remaining: int | None = None
    time_context_refresh_seconds = 15.0

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
            time_context = message.get("time_context")

            if isinstance(time_context, dict):
                raw_remaining = time_context.get("remaining_seconds")
                raw_elapsed = time_context.get("elapsed_seconds")
                raw_time_limit = time_context.get("time_limit_seconds")
                if (
                    isinstance(raw_remaining, int)
                    and isinstance(raw_elapsed, int)
                    and isinstance(raw_time_limit, int)
                ):
                    now = asyncio.get_running_loop().time()
                    remaining_minute = raw_remaining // 60
                    previous_remaining_minute = (
                        last_time_context_remaining // 60
                        if last_time_context_remaining is not None
                        else None
                    )
                    should_send_time_context = (
                        last_time_context_remaining is None
                        or remaining_minute != previous_remaining_minute
                        or now - last_time_context_sent_at >= time_context_refresh_seconds
                    )
                    if should_send_time_context:
                        live_request_queue.send_content(
                            content=Content(
                                role="user",
                                parts=[
                                    Part.from_text(
                                        text=(
                                            "Silent session timer context: "
                                            f"{raw_remaining} seconds remaining, "
                                            f"{raw_elapsed} seconds elapsed, "
                                            f"{raw_time_limit} seconds total. "
                                            "Use this only to pace the interview and nudge "
                                            "toward high-impact design areas when useful. "
                                            "Do not answer this packet directly."
                                        )
                                    )
                                ],
                            )
                        )
                        last_time_context_sent_at = now
                        last_time_context_remaining = raw_remaining

            if mime_type == "application/session-control":
                event_type = message.get("event")
                raw_time_limit = message.get("time_limit_seconds")
                time_limit_seconds = raw_time_limit if isinstance(raw_time_limit, int) else None

                if event_type == "session_started":
                    tracker.mark_started(time_limit_seconds)

                elif event_type == "time_warning":
                    raw_seconds_remaining = message.get("seconds_remaining")
                    if isinstance(raw_seconds_remaining, int):
                        tracker.mark_started(time_limit_seconds)
                        minutes_remaining = max(1, raw_seconds_remaining // 60)
                        warning_text = (
                            "Session timer update: briefly tell the candidate "
                            f"there are {minutes_remaining} minutes remaining, "
                            "then guide them to prioritize the highest-impact parts "
                            "of the system design discussion."
                        )
                        live_request_queue.send_content(
                            content=Content(
                                role="user",
                                parts=[Part.from_text(text=warning_text)],
                            )
                        )

                elif event_type == "session_ended":
                    reason = message.get("reason")
                    tracker.mark_ended(
                        reason if isinstance(reason, str) else None,
                        time_limit_seconds,
                    )

            elif mime_type == "text/plain":
                content = Content(role="user", parts=[Part.from_text(text=data)])
                live_request_queue.send_content(content=content)
                tracker.add_user_turn(data)
                logger.info("[CLIENT TO AGENT]: Text input received.")

            elif mime_type in ["audio/pcm", "image/jpeg", "image/png"]:
                decoded_data = base64.b64decode(data)
                live_request_queue.send_realtime(Blob(data=decoded_data, mime_type=mime_type))
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
    db: AsyncIOMotorDatabase,
    live_session_service: LiveSessionService | None = None,
):
    """
    Orchestrates a full bidirectional WebSocket session between a client and the
    ADK agent. Starts the agent session, then concurrently runs the send and
    receive loops until either side disconnects or an error occurs. Persists the
    conversation transcript to MongoDB when the session ends.

    Args:
        websocket: The accepted WebSocket connection to the client.
        user_id: Backend-generated unique identifier for the connected user.
        session_id: Frontend-generated unique identifier for this session.
    """
    live_events, live_request_queue = await start_agent_session(user_id, session_id, db)
    tracker = ConversationTracker(session_id=session_id, user_id=user_id, db=db)

    agent_task = asyncio.create_task(
        agent_to_client_messaging(websocket, live_events, tracker)
    )
    if live_session_service is None:
        client_task = asyncio.create_task(
            client_to_agent_messaging(websocket, live_request_queue, tracker)
        )
    else:
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

        for task in done:
            exc = task.exception()
            if exc:
                logger.error(f"Task error for client {user_id}: {exc}")
    finally:
        live_request_queue.close()
        await tracker.save()
        logger.info(f"Client {user_id} disconnected and queue closed.")
