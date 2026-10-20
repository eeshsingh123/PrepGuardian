import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import WebSocketException
from google.genai.types import Blob, Part

from app import prompts
from app.interview.tracks import InterviewType
from app.routes.agent import interview_options, websocket_endpoint
from app.schemas import LiveSessionConfig
from app.services.agent_service import build_run_config
from app.services.conversation_service import ConversationTracker
from app.services.interview_session import (
    CueScheduler,
    InterviewClock,
    build_clock_state,
    get_interview_status,
    save_interview_note,
)


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


class CueSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_scheduler_sends_phase_frames_and_partial_time_cues(self):
        now = FakeNow()
        clock = build_clock(now)
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

        self.assertEqual(len(live_request_queue.contents), 3)
        self.assertTrue(all(partial for _, partial in live_request_queue.contents))
        self.assertEqual(
            [content.parts[0].text for content, _ in live_request_queue.contents],
            [
                "cue:10:implementation",
                "cue:5:concurrency",
                "cue:2:extensibility",
            ],
        )

        clock_frames = [frame["session_clock"] for frame in websocket.frames]
        self.assertEqual(len(clock_frames), 7)
        self.assertEqual(clock_frames[0]["phase_key"], "requirements")
        self.assertEqual(clock_frames[0]["phase_index"], 0)
        self.assertEqual(clock_frames[-1]["phase_key"], "wrap_up")
        self.assertEqual(clock_frames[-1]["phase_index"], 6)
        self.assertEqual(clock_frames[-1]["phase_count"], 7)
        self.assertEqual(clock_frames[-1]["duration_seconds"], 1800)


class MultiPartEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_forwards_every_audio_part_and_records_usage(self):
        from app.services.agent_service import agent_to_client_messaging

        event = SimpleNamespace(
            output_transcription=SimpleNamespace(text="Hello there"),
            input_transcription=SimpleNamespace(text="Hi"),
            content=SimpleNamespace(
                parts=[
                    Part(inline_data=Blob(data=b"first", mime_type="audio/pcm")),
                    Part(inline_data=Blob(data=b"second", mime_type="audio/pcm")),
                    Part(text="partial text"),
                ]
            ),
            usage_metadata=SimpleNamespace(
                prompt_token_count=100,
                candidates_token_count=20,
                total_token_count=120,
            ),
            partial=True,
            turn_complete=True,
            interrupted=False,
        )

        async def live_events():
            yield event

        websocket = FakeWebSocket()
        tracker = ConversationTracker(
            session_id="sess_multi",
            user_id="pg_user",
            db=SimpleNamespace(),
        )

        await agent_to_client_messaging(websocket, live_events(), tracker)

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
                {"mime_type": "text/plain", "data": "Hello there", "is_transcript": True},
                {"mime_type": "text/plain", "data": "partial text"},
            ],
        )
        self.assertEqual(tracker.usage.prompt_tokens, 100)
        self.assertEqual(tracker.usage.response_tokens, 20)
        self.assertEqual(tracker.usage.total_tokens, 120)
        self.assertEqual(tracker.usage.turn_count, 1)
        self.assertEqual([turn["role"] for turn in tracker.turns], ["user", "agent"])


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


class WebSocketConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_interview_config_closes_before_accept(self):
        for interview_type, duration_minutes in (
            ("behavioral", 45),
            ("lld", 17),
        ):
            with self.subTest(
                interview_type=interview_type,
                duration_minutes=duration_minutes,
            ):
                with self.assertRaises(WebSocketException) as ctx:
                    await websocket_endpoint(
                        object(),
                        "sess_invalid",
                        token=None,
                        interview_type=interview_type,
                        duration_minutes=duration_minutes,
                    )
                self.assertEqual(ctx.exception.code, 1008)


class InterviewOptionsRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_options_are_built_from_tracks_and_allowed_durations(self):
        options = await interview_options(SimpleNamespace(user_id="pg_user"))

        self.assertEqual(options.durations_minutes, [30, 45, 60])
        self.assertEqual(options.default_duration_minutes, 45)
        self.assertEqual([track.type for track in options.tracks], ["lld", "hld"])
        self.assertEqual(options.tracks[0].title, "Low-Level Design")
        self.assertEqual(options.tracks[0].phases[0].key, "requirements")
        self.assertEqual(
            sum(phase.share for phase in options.tracks[0].phases),
            1.0,
        )


class LiveRunConfigTests(unittest.TestCase):
    def test_run_config_uses_live_tuning_settings(self):
        run_config = build_run_config()

        voice = run_config.speech_config.voice_config.prebuilt_voice_config
        self.assertEqual(voice.voice_name, "Kore")

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
        self.assertEqual(calls[-1][1]["$set"]["interview_type"], "lld")
        self.assertEqual(calls[-1][1]["$set"]["duration_minutes"], 30)
