import copy
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.schemas import ConversationResponse, ConversationTurn
from app.routes.conversations import generate_insights
from app.services import insight_service
from app.services.agent_service import run_bidirectional_session


@dataclass
class FakeSession:
    app_name: str
    user_id: str
    id: str
    state: dict = field(default_factory=dict)


class FakeInsightSessionService:
    def __init__(self):
        self.sessions: dict[tuple[str, str, str], FakeSession] = {}

    async def create_session(self, *, app_name: str, user_id: str, session_id: str, state: dict):
        stored_session = FakeSession(
            app_name=app_name,
            user_id=user_id,
            id=session_id,
            state=copy.deepcopy(state),
        )
        self.sessions[(app_name, user_id, session_id)] = stored_session
        return copy.deepcopy(stored_session)

    async def get_session(self, *, app_name: str, user_id: str, session_id: str):
        session = self.sessions.get((app_name, user_id, session_id))
        if session is None:
            return None
        return copy.deepcopy(session)


def build_fake_runner(state_update: dict):
    class FakeRunner:
        def __init__(self, *, app_name, agent, session_service):
            self.app_name = app_name
            self.agent = agent
            self.session_service = session_service

        async def run_async(self, *, user_id: str, session_id: str, new_message):
            stored_session = self.session_service.sessions[(self.app_name, user_id, session_id)]
            stored_session.state.update(copy.deepcopy(state_update))
            if False:
                yield None

    return FakeRunner


class InsightPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_insights_pipeline_reads_refreshed_session_state(self):
        fake_session_service = FakeInsightSessionService()
        runner_update = {
            "confidence_data": {
                "scores": [{"turn": 1, "score": 6, "note": "Recovered after hint"}],
                "peak_turn": 1,
                "drop_turn": 1,
                "average_score": 6.0,
                "trend": "stable",
            },
            "radar_data": {
                "pillars": {"Scalability": 6, "Caching": 3},
                "strongest": "Scalability",
                "weakest": "Caching",
                "avoided": ["Observability"],
            },
            "market_gap_data": {
                "target_role": "System Design Engineer",
                "target_company": "Top Tech Company",
                "target_level": "Mid-level",
                "dimensions": [
                    {
                        "name": "Independent Driving",
                        "market_bar": 5,
                        "candidate_score": 4,
                        "gap": 1,
                        "verdict": "close",
                    }
                ],
                "readiness_percentage": 72,
                "readiness_label": "Nearly Ready",
                "summary": "Solid breadth with clear room for more independent driving.",
            },
            "final_report": "```markdown\n# Report\n```",
        }

        candidate_profile = {
            "name": "Eesh Singh",
            "target_role": "System Design Engineer",
            "target_company": "Top Tech Company",
            "target_level": "Mid-level",
            "years_experience": "8 years",
            "session_date": "2026-03-15T07:17:30.237000",
        }

        with patch.object(insight_service, "session_service", fake_session_service), patch.object(
            insight_service,
            "Runner",
            build_fake_runner(runner_update),
        ):
            result = await insight_service.run_insights_pipeline(
                user_id="pg_user",
                session_id="sess_123",
                candidate_profile=candidate_profile,
                raw_transcript=[{"role": "user", "text": "hello"}],
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["confidence_data"]["average_score"], 6.0)
        self.assertEqual(result["radar_data"]["strongest"], "Scalability")
        self.assertEqual(result["market_gap_data"]["readiness_percentage"], 72)
        self.assertEqual(result["report_text"], "# Report")

    async def test_run_insights_pipeline_returns_none_for_blank_report_only(self):
        fake_session_service = FakeInsightSessionService()
        candidate_profile = {
            "name": "Eesh Singh",
            "target_role": "System Design Engineer",
            "target_company": "Top Tech Company",
            "target_level": "Mid-level",
            "years_experience": "8 years",
            "session_date": "2026-03-15T07:17:30.237000",
        }

        with patch.object(insight_service, "session_service", fake_session_service), patch.object(
            insight_service,
            "Runner",
            build_fake_runner({"final_report": "   "}),
        ):
            result = await insight_service.run_insights_pipeline(
                user_id="pg_user",
                session_id="sess_blank",
                candidate_profile=candidate_profile,
                raw_transcript=[{"role": "user", "text": "hello"}],
            )

        self.assertIsNone(result)


class LiveSessionPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_bidirectional_session_saves_transcript_without_generating_insights(self):
        saved_docs = []

        class FakeCollection:
            async def insert_one(self, doc):
                saved_docs.append(doc)

        fake_db = SimpleNamespace(conversations=FakeCollection())

        async def fake_agent_to_client_messaging(websocket, live_events, tracker):
            tracker.add_agent_turn("Start with requirements.")

        async def fake_client_to_agent_messaging(websocket, live_request_queue, tracker):
            tracker.add_user_turn("Let's design a notification system.")

        class FakeLiveRequestQueue:
            def close(self):
                return None

        with patch("app.services.agent_service.start_agent_session", AsyncMock(return_value=(object(), FakeLiveRequestQueue()))), patch(
            "app.services.agent_service.agent_to_client_messaging",
            side_effect=fake_agent_to_client_messaging,
        ), patch(
            "app.services.agent_service.client_to_agent_messaging",
            side_effect=fake_client_to_agent_messaging,
        ), patch(
            "app.services.conversation_service.get_mongo_db",
            return_value=fake_db,
        ), patch(
            "app.services.agent_service.get_user",
            AsyncMock(),
        ) as get_user_mock:
            await run_bidirectional_session(object(), "pg_user", "sess_live")

        self.assertEqual(len(saved_docs), 1)
        self.assertIsNone(saved_docs[0]["confidence_data"])
        self.assertIsNone(saved_docs[0]["radar_data"])
        self.assertIsNone(saved_docs[0]["market_gap_data"])
        self.assertIsNone(saved_docs[0]["report_text"])
        get_user_mock.assert_not_awaited()


class GenerateInsightsRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_insights_updates_existing_conversation_with_structured_payloads(self):
        conversation = ConversationResponse(
            session_id="sess_route",
            user_id="pg_user",
            started_at=datetime(2026, 3, 15, tzinfo=timezone.utc),
            ended_at=None,
            duration_seconds=120,
            turn_count=2,
            user_turn_count=1,
            agent_turn_count=1,
            turns=[
                ConversationTurn(
                    role="user",
                    text="Help me with system design.",
                    timestamp=datetime(2026, 3, 15, tzinfo=timezone.utc),
                ),
                ConversationTurn(
                    role="agent",
                    text="Let's start with requirements.",
                    timestamp=datetime(2026, 3, 15, tzinfo=timezone.utc),
                ),
            ],
            confidence_data=None,
            radar_data=None,
            market_gap_data=None,
            report_text=None,
        )

        insight_payload = {
            "confidence_data": {"average_score": 6.0, "scores": [], "peak_turn": 1, "drop_turn": 1, "trend": "stable"},
            "radar_data": {"pillars": {"Scalability": 6}, "strongest": "Scalability", "weakest": "Caching", "avoided": []},
            "market_gap_data": {
                "target_role": "System Design Engineer",
                "target_company": "Top Tech Company",
                "target_level": "Mid-level",
                "dimensions": [],
                "readiness_percentage": 65,
                "readiness_label": "Approaching Ready",
                "summary": "Needs more depth.",
            },
            "report_text": None,
        }

        with patch("app.routes.conversations.get_conversation_by_session", AsyncMock(return_value=conversation)), patch(
            "app.routes.conversations.get_user",
            AsyncMock(return_value=SimpleNamespace(
                name="Eesh Singh",
                preferences="System Design Engineer",
                experience="8 years",
                target_company=None,
                target_level=None,
            )),
        ), patch(
            "app.routes.conversations.run_insights_pipeline",
            AsyncMock(return_value=insight_payload),
        ) as run_pipeline_mock, patch(
            "app.routes.conversations.update_conversation_insights",
            AsyncMock(return_value=True),
        ) as update_mock:
            response = await generate_insights("sess_route", SimpleNamespace(user_id="pg_user"))

        self.assertEqual(response, {"ok": True})
        self.assertEqual(run_pipeline_mock.await_args.kwargs["candidate_profile"]["target_company"], "Top Tech Company")
        self.assertEqual(run_pipeline_mock.await_args.kwargs["candidate_profile"]["target_level"], "Mid-level")
        self.assertIsNone(update_mock.await_args.kwargs["report_text"])
        self.assertEqual(
            update_mock.await_args.kwargs["confidence_data"],
            insight_payload["confidence_data"],
        )

    async def test_generate_insights_raises_when_pipeline_returns_no_outputs(self):
        conversation = ConversationResponse(
            session_id="sess_route",
            user_id="pg_user",
            started_at=datetime(2026, 3, 15, tzinfo=timezone.utc),
            ended_at=None,
            duration_seconds=120,
            turn_count=1,
            user_turn_count=1,
            agent_turn_count=0,
            turns=[
                ConversationTurn(
                    role="user",
                    text="Help me with system design.",
                    timestamp=datetime(2026, 3, 15, tzinfo=timezone.utc),
                )
            ],
            confidence_data=None,
            radar_data=None,
            market_gap_data=None,
            report_text=None,
        )

        with patch("app.routes.conversations.get_conversation_by_session", AsyncMock(return_value=conversation)), patch(
            "app.routes.conversations.get_user",
            AsyncMock(return_value=SimpleNamespace(
                name="Eesh Singh",
                preferences="System Design Engineer",
                experience="8 years",
                target_company=None,
                target_level=None,
            )),
        ), patch(
            "app.routes.conversations.run_insights_pipeline",
            AsyncMock(return_value=None),
        ), patch(
            "app.routes.conversations.update_conversation_insights",
            AsyncMock(),
        ) as update_mock:
            with self.assertRaises(HTTPException) as ctx:
                await generate_insights("sess_route", SimpleNamespace(user_id="pg_user"))

        self.assertEqual(ctx.exception.status_code, 503)
        update_mock.assert_not_awaited()

