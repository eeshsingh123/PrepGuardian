import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, WebSocketException
from google.adk.flows.llm_flows.tools._agent_tools import mark_live_async_tools_non_blocking
from google.adk.flows.llm_flows.tools._caller import _build_function_response_content
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from google.genai.types import Blob, Part

from app import prompts
from app.constants import RedisConstants
from app.interview.tracks import InterviewType
from app.routes.agent import create_session, interview_options, websocket_endpoint
from app.schemas import LiveSessionConfig
from app.services.agent_service import build_candidate_state, build_run_config
from app.services.conversation_service import ConversationTracker
from app.services.interview_session import (
    CueScheduler,
    InterviewClock,
    build_clock_state,
    build_interview_tools,
    candidate_context_from_state,
    get_interview_status,
    save_interview_note,
)
from app.services.live_session_service import LiveSessionTicket


START = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


class FakeNow:
    def __init__(self, current: datetime = START):
        self.current = current

    def __call__(self) -> datetime:
        return self.current


class FakeWebSocket:
    def __init__(self):
        self.frames = []

    async def send_text(self, payload: str):
        self.frames.append(json.loads(payload))


class FakeLiveRequestQueue:
    def __init__(self):
        self.contents = []
        self.realtime = []

    def send_content(self, content, partial=False):
        self.contents.append((content, partial))

    def send_realtime(self, blob):
        self.realtime.append(blob)


def build_clock(now: FakeNow, duration_minutes: int = 30) -> InterviewClock:
    config = LiveSessionConfig(
        interview_type=InterviewType.LLD,
        duration_minutes=duration_minutes,
    )
    return InterviewClock(config, started_at=START, now=now)


class InterviewClockTests(unittest.TestCase):
    def test_clock_reports_elapsed_remaining_and_current_phase(self):
        now = FakeNow()
        clock = build_clock(now)

        self.assertEqual(clock.elapsed_seconds, 0)
        self.assertEqual(clock.remaining_seconds, 1800)
        self.assertEqual(clock.current_window.phase.key, "requirements")
        self.assertEqual(clock.current_phase_index, 0)

        now.current = START + timedelta(seconds=300)

        self.assertEqual(clock.elapsed_seconds, 300)
        self.assertEqual(clock.remaining_seconds, 1500)
        self.assertEqual(clock.current_window.phase.key, "entities")
        self.assertEqual(clock.current_phase_index, 1)
        self.assertEqual(clock.next_window.phase.title, "Class Design")

    def test_clock_clamps_after_duration(self):
        now = FakeNow()
        clock = build_clock(now)
        now.current = START + timedelta(seconds=2000)

        self.assertEqual(clock.remaining_seconds, 0)
        self.assertEqual(clock.current_window.phase.key, "wrap_up")
        self.assertIsNone(clock.next_window)


class InterviewToolTests(unittest.TestCase):
    def test_status_reads_state_and_reports_next_phase(self):
        started_at = datetime.now(timezone.utc) - timedelta(seconds=300)
        clock = InterviewClock(
            LiveSessionConfig(interview_type=InterviewType.LLD, duration_minutes=30),
            started_at=started_at,
        )
        context = SimpleNamespace(state=build_clock_state(clock))

        status = get_interview_status(context)

        self.assertEqual(status["elapsed_minutes"], 5)
        self.assertEqual(status["remaining_minutes"], 25)
        self.assertEqual(status["phase_key"], "entities")
        self.assertEqual(status["phase_title"], "Entities & Relationships")
        self.assertEqual(status["minutes_left_in_phase"], 1)
        self.assertEqual(status["next_phase_title"], "Class Design")
        self.assertEqual(status["notes"], [])

    def test_notes_persist_in_session_state_and_survive_status_reads(self):
        now = FakeNow()
        clock = build_clock(now)
        context = SimpleNamespace(state=build_clock_state(clock))

        first = save_interview_note("  Scope: notifications only  ", context)
        second = save_interview_note("Entities: User, Notification, Channel", context)
        blank = save_interview_note("   ", context)

        self.assertEqual(first, {"saved": True, "note_count": 1})
        self.assertEqual(second, {"saved": True, "note_count": 2})
        self.assertEqual(blank, {"saved": False, "note_count": 2})
        self.assertEqual(
            get_interview_status(context)["notes"],
            [
                "Scope: notifications only",
                "Entities: User, Notification, Channel",
            ],
        )

    def test_notes_are_trimmed_and_capped(self):
        context = SimpleNamespace(state={})

        save_interview_note("x" * 350, context)
        self.assertEqual(len(context.state["interviewer_notes"][0]), 300)

        for index in range(1, 40):
            save_interview_note(f"note {index}", context)

        overflow = save_interview_note("one note too many", context)

        self.assertEqual(overflow, {"saved": False, "note_count": 40})
        self.assertEqual(len(context.state["interviewer_notes"]), 40)


class CandidateStateTests(unittest.TestCase):
    def test_unknown_profile_fields_stay_blank(self):
        user = SimpleNamespace(
            name=None,
            experience="",
            target_company=None,
            target_level="   ",
            preferences=None,
        )

        state = build_candidate_state(user)

        self.assertEqual(
            state,
            {
                "user_name": "",
                "user_experience": "",
                "user_preferences": "",
                "user_target_company": "",
                "user_target_level": "",
            },
        )
        candidate = candidate_context_from_state(state)
        self.assertEqual(
            [
                candidate.name,
                candidate.experience,
                candidate.preferences,
                candidate.target_company,
                candidate.target_level,
            ],
            ["", "", "", "", ""],
        )

    def test_known_profile_fields_are_trimmed(self):
        user = SimpleNamespace(
            name=" Eesh ",
            experience=" 8 years ",
            target_company="Google",
            target_level="Senior",
            preferences=" LLD ",
        )

        state = build_candidate_state(user)

        self.assertEqual(state["user_name"], "Eesh")
        self.assertEqual(state["user_experience"], "8 years")
        self.assertEqual(state["user_preferences"], "LLD")
        self.assertEqual(state["user_target_company"], "Google")
        self.assertEqual(state["user_target_level"], "Senior")


class CueSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def run_scheduler(
        self,
        interview_type: InterviewType,
        duration_minutes: int = 30,
    ) -> tuple[FakeWebSocket, FakeLiveRequestQueue]:
        now = FakeNow()
        clock = InterviewClock(
            LiveSessionConfig(
                interview_type=interview_type,
                duration_minutes=duration_minutes,
            ),
            started_at=START,
            now=now,
        )
        websocket = FakeWebSocket()
        live_request_queue = FakeLiveRequestQueue()

        async def fake_sleep(seconds: float):
            now.current += timedelta(seconds=seconds)

        def fake_clock_cue(minutes: int, window, track) -> str:
            return f"cue:{minutes}:{window.phase.key}"

        scheduler = CueScheduler(
            clock,
            websocket,
            live_request_queue,
            sleep=fake_sleep,
        )

        with patch.object(
            prompts,
            "build_clock_cue",
            side_effect=fake_clock_cue,
            create=True,
        ):
            await scheduler.run()

        return websocket, live_request_queue

    async def test_scheduler_sends_start_cue_then_phase_frames_and_partial_cues(self):
        websocket, live_request_queue = await self.run_scheduler(InterviewType.LLD)

        contents = live_request_queue.contents
        self.assertEqual(len(contents), 9)
        self.assertFalse(contents[0][1])
        self.assertEqual(
            contents[0][0].parts[0].text,
            prompts.build_session_start_cue(),
        )
        self.assertTrue(all(partial for _, partial in contents[1:]))
        self.assertEqual(
            [content.parts[0].text for content, _ in contents[1:]],
            [
                "cue:27:entities",
                "cue:24:class_design",
                "cue:15:implementation",
                "cue:10:implementation",
                "cue:8:concurrency",
                "cue:5:concurrency",
                "cue:4:extensibility",
                "cue:2:extensibility",
            ],
        )

        clock_frames = [frame["session_clock"] for frame in websocket.frames]
        self.assertEqual(len(clock_frames), 7)
        self.assertEqual(clock_frames[0]["phase_key"], "requirements")
        self.assertEqual(clock_frames[0]["phase_index"], 0)
        self.assertEqual(clock_frames[0]["elapsed_seconds"], 0)
        self.assertEqual(clock_frames[1]["phase_key"], "entities")
        self.assertEqual(clock_frames[1]["elapsed_seconds"], 216)
        self.assertEqual(clock_frames[-1]["phase_key"], "wrap_up")
        self.assertEqual(clock_frames[-1]["phase_index"], 6)
        self.assertEqual(clock_frames[-1]["phase_count"], 7)
        self.assertEqual(clock_frames[-1]["duration_seconds"], 1800)
        self.assertTrue(all("started_at" in frame for frame in clock_frames))

    async def test_phase_cue_is_skipped_when_a_minute_cue_is_within_thirty_seconds(self):
        websocket, live_request_queue = await self.run_scheduler(InterviewType.HLD)

        contents = live_request_queue.contents
        self.assertEqual(len(contents), 7)
        self.assertFalse(contents[0][1])
        self.assertEqual(
            contents[0][0].parts[0].text,
            prompts.build_session_start_cue(),
        )
        self.assertTrue(all(partial for _, partial in contents[1:]))
        self.assertEqual(
            [content.parts[0].text for content, _ in contents[1:]],
            [
                "cue:26:entities_api",
                "cue:23:high_level_design",
                "cue:14:deep_dives",
                "cue:10:deep_dives",
                "cue:5:concurrency",
                "cue:2:concurrency",
            ],
        )

        clock_frames = [frame["session_clock"] for frame in websocket.frames]
        self.assertEqual(len(clock_frames), 6)
        self.assertEqual(clock_frames[-1]["phase_key"], "wrap_up")
        self.assertEqual(clock_frames[-1]["elapsed_seconds"], 1692)


class TranscriptionEventTests(unittest.IsolatedAsyncioTestCase):
    def build_event(
        self,
        *,
        input_text: str | None = None,
        output_text: str | None = None,
        finished: bool = True,
        partial: bool | None = None,
        turn_complete: bool = False,
        usage=None,
        parts: list[Part] | None = None,
    ):
        return SimpleNamespace(
            output_transcription=(
                SimpleNamespace(text=output_text, finished=finished)
                if output_text is not None
                else None
            ),
            input_transcription=(
                SimpleNamespace(text=input_text, finished=finished)
                if input_text is not None
                else None
            ),
            content=SimpleNamespace(parts=parts) if parts else None,
            usage_metadata=usage,
            partial=not finished if partial is None else partial,
            turn_complete=turn_complete,
            interrupted=False,
        )

    async def run_events(self, events):
        from app.services.agent_service import agent_to_client_messaging

        async def live_events():
            for event in events:
                yield event

        websocket = FakeWebSocket()
        tracker = ConversationTracker(
            session_id="sess_transcript",
            user_id="pg_user",
            db=SimpleNamespace(),
        )
        await agent_to_client_messaging(websocket, live_events(), tracker)
        return websocket, tracker

    async def test_agent_forwards_every_audio_part_and_records_usage(self):
        event = self.build_event(
            input_text="Hi",
            output_text="Hello there",
            partial=True,
            turn_complete=True,
            usage=SimpleNamespace(
                prompt_token_count=100,
                candidates_token_count=20,
                total_token_count=120,
            ),
            parts=[
                Part(inline_data=Blob(data=b"first", mime_type="audio/pcm")),
                Part(inline_data=Blob(data=b"second", mime_type="audio/pcm")),
                Part(text="partial text"),
            ],
        )

        websocket, tracker = await self.run_events([event])

        audio_frames = [
            frame for frame in websocket.frames if frame.get("mime_type") == "audio/pcm"
        ]
        self.assertEqual(len(audio_frames), 2)
        self.assertEqual(
            [
                frame
                for frame in websocket.frames
                if frame.get("mime_type") == "text/plain"
            ],
            [
                {
                    "mime_type": "text/plain",
                    "data": "Hello there",
                    "is_transcript": True,
                    "partial": False,
                },
                {"mime_type": "text/plain", "data": "partial text"},
            ],
        )
        self.assertEqual(tracker.usage.prompt_tokens, 100)
        self.assertEqual(tracker.usage.response_tokens, 20)
        self.assertEqual(tracker.usage.total_tokens, 120)
        self.assertEqual(tracker.usage.turn_count, 1)
        self.assertEqual(
            [(turn["role"], turn["text"]) for turn in tracker.turns],
            [("user", "Hi"), ("agent", "Hello there")],
        )

    async def test_partial_transcription_chunks_are_forwarded_but_only_final_is_saved(self):
        events = [
            self.build_event(input_text="Hi", finished=True),
            self.build_event(output_text="Hello", finished=False),
            self.build_event(output_text=" there", finished=False),
            self.build_event(output_text="Hello there", finished=True),
            self.build_event(turn_complete=True),
        ]

        websocket, tracker = await self.run_events(events)

        transcript_frames = [
            frame
            for frame in websocket.frames
            if frame.get("is_transcript") is True
        ]
        self.assertEqual(
            [(frame["data"], frame["partial"]) for frame in transcript_frames],
            [("Hello", True), (" there", True), ("Hello there", False)],
        )
        self.assertEqual(
            [(turn["role"], turn["text"]) for turn in tracker.turns],
            [("user", "Hi"), ("agent", "Hello there")],
        )

    async def test_partial_agent_chunks_fall_back_to_concatenation(self):
        events = [
            self.build_event(output_text="Hello", finished=False),
            self.build_event(output_text=" there", finished=False),
            self.build_event(turn_complete=True),
        ]

        _, tracker = await self.run_events(events)

        self.assertEqual(
            [(turn["role"], turn["text"]) for turn in tracker.turns],
            [("agent", "Hello there")],
        )

    async def test_partial_input_chunks_fall_back_to_concatenation(self):
        events = [
            self.build_event(input_text="Hi", finished=False),
            self.build_event(input_text=" there", finished=False),
            self.build_event(turn_complete=True),
        ]

        websocket, tracker = await self.run_events(events)

        self.assertEqual(
            [(turn["role"], turn["text"]) for turn in tracker.turns],
            [("user", "Hi there")],
        )
        self.assertEqual(
            [
                frame
                for frame in websocket.frames
                if frame.get("is_transcript") is True
            ],
            [],
        )


class UsageAccumulationTests(unittest.TestCase):
    def test_usage_snapshots_accumulate_once_per_model_turn(self):
        tracker = ConversationTracker(
            session_id="sess_usage",
            user_id="pg_user",
            db=SimpleNamespace(),
        )

        tracker.record_usage(
            SimpleNamespace(
                prompt_token_count=100,
                candidates_token_count=20,
                total_token_count=120,
            )
        )
        tracker.record_model_turn()
        tracker.record_usage(
            SimpleNamespace(
                prompt_token_count=180,
                candidates_token_count=30,
                total_token_count=210,
            )
        )
        tracker.record_usage(
            SimpleNamespace(
                prompt_token_count=180,
                candidates_token_count=35,
                total_token_count=215,
            )
        )
        tracker.record_model_turn()

        self.assertEqual(tracker.usage.prompt_tokens, 280)
        self.assertEqual(tracker.usage.response_tokens, 55)
        self.assertEqual(tracker.usage.total_tokens, 335)
        self.assertEqual(tracker.usage.turn_count, 2)


class ToolSchedulingTests(unittest.TestCase):
    def test_interview_tools_declare_non_blocking_and_set_scheduling(self):
        tools = build_interview_tools()

        self.assertEqual(
            [tool.response_scheduling for tool in tools],
            [
                types.FunctionResponseScheduling.WHEN_IDLE,
                types.FunctionResponseScheduling.SILENT,
            ],
        )
        self.assertTrue(
            all(tool.behavior is types.Behavior.NON_BLOCKING for tool in tools)
        )

        declarations = [tool._get_declaration() for tool in tools]
        request = LlmRequest(
            config=types.GenerateContentConfig(
                tools=[types.Tool(function_declarations=declarations)]
            ),
            tools_dict={tool.name: tool for tool in tools},
        )
        mark_live_async_tools_non_blocking(request)

        self.assertTrue(
            all(
                declaration.behavior is types.Behavior.NON_BLOCKING
                for declaration in declarations
            )
        )

    def test_function_responses_carry_scheduling(self):
        tools = build_interview_tools()
        expected_scheduling = [
            types.FunctionResponseScheduling.WHEN_IDLE,
            types.FunctionResponseScheduling.SILENT,
        ]

        for tool, scheduling in zip(tools, expected_scheduling):
            content = _build_function_response_content(
                tool,
                {"saved": True},
                "call-1",
            )
            function_response = content.parts[0].function_response
            self.assertIsNotNone(function_response)
            self.assertEqual(function_response.scheduling, scheduling)
            self.assertEqual(function_response.id, "call-1")


class WebSocketConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_or_invalid_ticket_closes_before_accept(self):
        class EmptyRedis:
            async def getdel(self, key):
                return None

        websocket = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(redis=EmptyRedis(), mongo_db=object())
            )
        )

        for ticket in (None, "unknown"):
            with self.subTest(ticket=ticket):
                with self.assertRaises(WebSocketException) as ctx:
                    await websocket_endpoint(websocket, ticket=ticket)
                self.assertEqual(ctx.exception.code, 1008)

    async def test_valid_ticket_opens_the_session_for_its_issuing_user(self):
        class FakeRedis:
            def __init__(self):
                self.values = {
                    "pg:live-session:pg_user": "sess_server",
                }
                self.ttls = {}
                self.deleted = []

            async def getdel(self, key):
                return self.values.pop(key, None)

            async def get(self, key):
                return self.values.get(key)

            async def set(self, key, value, ex=None, nx=False):
                self.values[key] = value
                return True

            async def expire(self, key, ttl):
                self.ttls[key] = ttl
                return True

            async def delete(self, key):
                self.deleted.append(key)
                self.values.pop(key, None)
                return 1

        redis = FakeRedis()
        redis.values["pg:ws-ticket:good-ticket"] = LiveSessionTicket(
            user_id="pg_user",
            session_id="sess_server",
            interview_type=InterviewType.HLD,
            duration_minutes=60,
        ).model_dump_json()

        class FakeWebSocket:
            def __init__(self):
                self.app = SimpleNamespace(
                    state=SimpleNamespace(redis=redis, mongo_db=object())
                )
                self.accepted = False
                self.closed_code = None

            async def accept(self):
                self.accepted = True

            async def close(self, code=1000):
                self.closed_code = code

        websocket = FakeWebSocket()
        with patch(
            "app.routes.agent.run_bidirectional_session",
            AsyncMock(),
        ) as run_session:
            await websocket_endpoint(websocket, ticket="good-ticket")

        self.assertTrue(websocket.accepted)
        self.assertEqual(websocket.closed_code, 1000)
        self.assertNotIn("pg:ws-ticket:good-ticket", redis.values)
        self.assertEqual(run_session.await_args.args[1], "pg_user")
        self.assertEqual(run_session.await_args.args[2], "sess_server")
        self.assertEqual(run_session.await_args.args[3].interview_type, InterviewType.HLD)
        self.assertEqual(run_session.await_args.args[3].duration_minutes, 60)


class InterviewOptionsRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_options_are_built_from_tracks_and_allowed_durations(self):
        options = await interview_options(SimpleNamespace(user_id="pg_user"))

        self.assertEqual(options.interviewer_name, "Aiden")
        self.assertEqual(options.durations_minutes, [30, 45, 60])
        self.assertEqual(options.default_duration_minutes, 45)
        self.assertEqual([track.type for track in options.tracks], ["lld", "hld"])
        self.assertEqual(options.tracks[0].title, "Low-Level Design")
        self.assertEqual(options.tracks[0].phases[0].key, "requirements")
        self.assertEqual(
            sum(phase.share for phase in options.tracks[0].phases),
            1.0,
        )


class SessionRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_session_returns_server_id_and_ticket(self):
        class FakeRedis:
            def __init__(self):
                self.values = {}
                self.ttls = {}

            async def set(self, key, value, ex=None, nx=False):
                if nx and key in self.values:
                    return False
                self.values[key] = value
                self.ttls[key] = ex
                return True

        redis = FakeRedis()
        config = LiveSessionConfig(
            interview_type=InterviewType.HLD,
            duration_minutes=60,
        )

        response = await create_session(
            config,
            SimpleNamespace(user_id="pg_user"),
            redis,
        )

        self.assertTrue(response.session_id.startswith("sess_"))
        self.assertEqual(len(response.session_id), len("sess_") + 32)
        self.assertEqual(response.expires_in, RedisConstants.WS_TICKET_TTL_SECONDS)

        active_key = f"{RedisConstants.ACTIVE_SESSION_PREFIX}:pg_user"
        self.assertEqual(redis.values[active_key], response.session_id)
        self.assertEqual(
            redis.ttls[active_key],
            RedisConstants.ACTIVE_SESSION_TTL_SECONDS,
        )

        ticket_key = f"{RedisConstants.WS_TICKET_PREFIX}:{response.ticket}"
        self.assertEqual(
            json.loads(redis.values[ticket_key]),
            {
                "user_id": "pg_user",
                "session_id": response.session_id,
                "interview_type": "hld",
                "duration_minutes": 60,
            },
        )
        self.assertEqual(
            redis.ttls[ticket_key],
            RedisConstants.WS_TICKET_TTL_SECONDS,
        )

    async def test_create_session_rejects_an_active_session(self):
        class FakeRedis:
            def __init__(self):
                self.values = {f"{RedisConstants.ACTIVE_SESSION_PREFIX}:pg_user": "sess_old"}

            async def set(self, key, value, ex=None, nx=False):
                if nx and key in self.values:
                    return False
                self.values[key] = value
                return True

        with self.assertRaises(HTTPException) as ctx:
            await create_session(
                LiveSessionConfig(),
                SimpleNamespace(user_id="pg_user"),
                FakeRedis(),
            )

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail, "active_session")


class LiveRunConfigTests(unittest.TestCase):
    def test_run_config_uses_live_tuning_settings(self):
        run_config = build_run_config()

        voice = run_config.speech_config.voice_config.prebuilt_voice_config
        self.assertEqual(voice.voice_name, "Charon")

        activity = run_config.realtime_input_config.automatic_activity_detection
        self.assertEqual(activity.silence_duration_ms, 1200)
        self.assertEqual(activity.prefix_padding_ms, 20)

        self.assertEqual(run_config.context_window_compression.trigger_tokens, 32000)
        self.assertEqual(
            run_config.context_window_compression.sliding_window.target_tokens,
            16000,
        )
        self.assertIsNotNone(run_config.input_audio_transcription)
        self.assertIsNotNone(run_config.output_audio_transcription)
        self.assertIsNotNone(run_config.session_resumption)


class ConversationUpsertTests(unittest.IsolatedAsyncioTestCase):
    async def test_saving_the_same_session_twice_upserts_instead_of_inserting(self):
        calls = []

        class FakeCollection:
            async def update_one(self, query, update, upsert=False):
                calls.append((query, update, upsert))

        config = LiveSessionConfig(duration_minutes=30)
        tracker = ConversationTracker(
            session_id="sess_reconnect",
            user_id="pg_user",
            db=SimpleNamespace(conversations=FakeCollection()),
            config=config,
        )
        tracker.add_user_turn("Let's design a notification service.")

        await tracker.save()
        await tracker.save()

        self.assertEqual(len(calls), 2)
        self.assertTrue(all(upsert for _, _, upsert in calls))
        self.assertEqual({query["session_id"] for query, _, _ in calls}, {"sess_reconnect"})
        self.assertEqual({query["user_id"] for query, _, _ in calls}, {"pg_user"})
        self.assertEqual(calls[-1][1]["$set"]["interview_type"], "lld")
        self.assertEqual(calls[-1][1]["$set"]["duration_minutes"], 30)

    async def test_only_allowed_end_reasons_are_saved(self):
        saved_docs = []

        class FakeCollection:
            async def update_one(self, query, update, upsert=False):
                saved_docs.append(update["$set"])

        tracker = ConversationTracker(
            session_id="sess_reason",
            user_id="pg_user",
            db=SimpleNamespace(conversations=FakeCollection()),
        )
        tracker.add_user_turn("Hello")
        tracker.mark_ended("something_else")
        await tracker.save()

        tracker.mark_ended("time_limit")
        await tracker.save()

        self.assertEqual(saved_docs[0]["ended_reason"], "websocket_closed")
        self.assertEqual(saved_docs[1]["ended_reason"], "time_limit")
