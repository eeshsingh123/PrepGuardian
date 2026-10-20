from datetime import datetime, timezone

from google.genai.types import GenerateContentResponseUsageMetadata
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.logger import logger
from app.schemas import (
    ConversationTurn,
    ConversationResponse,
    ConversationSummaryResponse,
)
from app.schemas.conversations import SessionUsage
from app.schemas.live import LiveSessionConfig


class ConversationTracker:
    """
    Accumulates conversation turns and usage in memory during a live session.

    Args:
        session_id: Frontend-generated unique session identifier.
        user_id: Backend-generated user identifier.
        db: MongoDB database used when the session is saved.
        config: Interview type and duration chosen by the candidate.
        started_at: Server clock start; defaults to the current UTC time.
    """

    def __init__(
        self,
        session_id: str,
        user_id: str,
        db: AsyncIOMotorDatabase,
        config: LiveSessionConfig | None = None,
        started_at: datetime | None = None,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.db = db
        self.started_at = started_at or datetime.now(timezone.utc)
        self.turns: list[dict] = []
        self.interview_type = config.interview_type.value if config else None
        self.duration_minutes = config.duration_minutes if config else None
        self.time_limit_seconds = config.duration_seconds if config else None
        self.interviewer_notes: list[str] = []
        self.usage = SessionUsage()
        self.pending_usage: SessionUsage | None = None
        self.ended_reason: str | None = None

    def mark_ended(self, reason: str | None = None):
        if reason:
            self.ended_reason = reason

    def add_user_turn(self, text: str):
        if not text or not text.strip():
            return

        stripped_text = text.strip()

        # Deduplicate consecutive identical user messages (often triggered by ADK intermediate transcripts)
        if self.turns and self.turns[-1]["role"] == "user" and self.turns[-1]["text"] == stripped_text:
            return

        self.turns.append({
            "role": "user",
            "text": stripped_text,
            "timestamp": datetime.now(timezone.utc),
        })

    def add_agent_turn(self, text: str):
        if not text or not text.strip():
            return
        self.turns.append({
            "role": "agent",
            "text": text.strip(),
            "timestamp": datetime.now(timezone.utc),
        })

    def record_usage(self, metadata: GenerateContentResponseUsageMetadata):
        """
        Keeps the latest usage snapshot of the current turn. Live usage metadata
        describes one generation request, so repeated snapshots must not be summed.
        """
        prompt_tokens = metadata.prompt_token_count or 0
        response_tokens = metadata.candidates_token_count or 0
        self.pending_usage = SessionUsage(
            prompt_tokens=prompt_tokens,
            response_tokens=response_tokens,
            total_tokens=metadata.total_token_count or (prompt_tokens + response_tokens),
        )

    def record_model_turn(self):
        self.commit_pending_usage()
        self.usage.turn_count += 1

    def commit_pending_usage(self):
        """
        Adds the finished turn's snapshot to the session totals. Every Live turn
        re-bills the whole context, so summing one snapshot per turn mirrors cost.
        """
        if self.pending_usage is None:
            return
        self.usage.prompt_tokens += self.pending_usage.prompt_tokens
        self.usage.response_tokens += self.pending_usage.response_tokens
        self.usage.total_tokens += self.pending_usage.total_tokens
        self.pending_usage = None

    async def save(
        self,
        confidence_data: dict | None = None,
        radar_data: dict | None = None,
        market_gap_data: dict | None = None,
        report_text: str | None = None,
        interviewer_notes: list[str] | None = None,
    ):
        """
        Persists the accumulated conversation to MongoDB. Calculates metadata
        like duration, turn counts, and timestamps. Skips saving if no turns
        were recorded (e.g. user connected but never spoke).
        """
        if not self.turns:
            logger.info(
                f"Session '{self.session_id}' had no turns, skipping save."
            )
            return

        self.commit_pending_usage()
        ended_at = datetime.now(timezone.utc)
        duration_seconds = int((ended_at - self.started_at).total_seconds())
        user_turn_count = sum(1 for t in self.turns if t["role"] == "user")
        agent_turn_count = sum(1 for t in self.turns if t["role"] == "agent")

        conversation_doc = {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "started_at": self.started_at,
            "ended_at": ended_at,
            "duration_seconds": duration_seconds,
            "time_limit_seconds": self.time_limit_seconds,
            "ended_reason": self.ended_reason or "websocket_closed",
            "turn_count": len(self.turns),
            "user_turn_count": user_turn_count,
            "agent_turn_count": agent_turn_count,
            "interview_type": self.interview_type,
            "duration_minutes": self.duration_minutes,
            "interviewer_notes": interviewer_notes or self.interviewer_notes,
            "usage": self.usage.model_dump(),
            "turns": self.turns,
        }

        update = {"$set": conversation_doc}
        if confidence_data is not None:
            update["$set"]["confidence_data"] = confidence_data
        if radar_data is not None:
            update["$set"]["radar_data"] = radar_data
        if market_gap_data is not None:
            update["$set"]["market_gap_data"] = market_gap_data
        if report_text is not None:
            update["$set"]["report_text"] = report_text

        await self.db.conversations.update_one(
            {"session_id": self.session_id},
            update,
            upsert=True,
        )
        logger.info(
            f"Conversation saved: session='{self.session_id}', "
            f"turns={len(self.turns)}, duration={duration_seconds}s, "
            f"usage_prompt={self.usage.prompt_tokens}, "
            f"usage_response={self.usage.response_tokens}, "
            f"usage_total={self.usage.total_tokens}, "
            f"model_turns={self.usage.turn_count}"
        )


async def get_conversations_by_user(user_id: str, db: AsyncIOMotorDatabase) -> list[ConversationSummaryResponse]:
    """
    Fetches all conversation summaries for a given user, sorted by
    started_at descending (newest first). Returns a lightweight preview
    using the first agent turn's text.

    Args:
        user_id: Backend-generated user identifier.

    Returns:
        List of ConversationSummaryResponse sorted newest first.
    """
    cursor = db.conversations.find(
        {"user_id": user_id},
        {
            "session_id": 1,
            "user_id": 1,
            "started_at": 1,
            "ended_at": 1,
            "duration_seconds": 1,
            "time_limit_seconds": 1,
            "ended_reason": 1,
            "turn_count": 1,
            "turns": 1,
            "_id": 0,
        },
    ).sort("started_at", -1)

    summaries = []
    async for doc in cursor:
        # Extract a preview from the first agent turn for the list view
        preview = ""
        for turn in doc.get("turns", []):
            if turn["role"] == "agent":
                preview = turn["text"][:120]
                break

        summaries.append(
            ConversationSummaryResponse(
                session_id=doc["session_id"],
                user_id=doc["user_id"],
                started_at=doc["started_at"],
                ended_at=doc.get("ended_at"),
                duration_seconds=doc.get("duration_seconds", 0),
                time_limit_seconds=doc.get("time_limit_seconds"),
                ended_reason=doc.get("ended_reason"),
                turn_count=doc.get("turn_count", 0),
                preview=preview,
            )
        )
    return summaries


async def get_conversation_by_session(session_id: str, db: AsyncIOMotorDatabase) -> ConversationResponse | None:
    """
    Fetches a single full conversation document by its session_id.

    Args:
        session_id: The unique session identifier.

    Returns:
        ConversationResponse with all turns, or None if not found.
    """
    doc = await db.conversations.find_one(
        {"session_id": session_id}, {"_id": 0}
    )
    if not doc:
        return None

    turns = [ConversationTurn(**t) for t in doc.get("turns", [])]
    return ConversationResponse(
        session_id=doc["session_id"],
        user_id=doc["user_id"],
        started_at=doc["started_at"],
        ended_at=doc.get("ended_at"),
        duration_seconds=doc.get("duration_seconds", 0),
        time_limit_seconds=doc.get("time_limit_seconds"),
        ended_reason=doc.get("ended_reason"),
        turn_count=doc.get("turn_count", 0),
        user_turn_count=doc.get("user_turn_count", 0),
        agent_turn_count=doc.get("agent_turn_count", 0),
        interview_type=doc.get("interview_type"),
        duration_minutes=doc.get("duration_minutes"),
        interviewer_notes=doc.get("interviewer_notes", []),
        usage=doc.get("usage"),
        turns=turns,
        confidence_data=doc.get("confidence_data"),
        radar_data=doc.get("radar_data"),
        market_gap_data=doc.get("market_gap_data"),
        report_text=doc.get("report_text"),
    )


async def update_conversation_insights(
    session_id: str,
    *,
    confidence_data: dict | None = None,
    radar_data: dict | None = None,
    market_gap_data: dict | None = None,
    report_text: str | None = None,
    db: AsyncIOMotorDatabase,
) -> bool:
    """
    Updates an existing conversation document with insight pipeline results.
    Only the four insight fields are set; turns and metadata are unchanged.

    Returns:
        True if a document was matched and updated.
    """
    update = {"$set": {}}
    if confidence_data is not None:
        update["$set"]["confidence_data"] = confidence_data
    if radar_data is not None:
        update["$set"]["radar_data"] = radar_data
    if market_gap_data is not None:
        update["$set"]["market_gap_data"] = market_gap_data
    if report_text is not None:
        update["$set"]["report_text"] = report_text
    if not update["$set"]:
        return False
    result = await db.conversations.update_one(
        {"session_id": session_id},
        update,
    )
    if result.modified_count:
        logger.info(f"Updated insights for session '{session_id}'.")
    return result.modified_count > 0
