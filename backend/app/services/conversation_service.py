from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase
from app.logger import logger
from app.schemas import (
    ConversationTurn,
    ConversationResponse,
    ConversationSummaryResponse,
)


class ConversationTracker:
    """
    Accumulates conversation turns in memory during a live WebSocket session.
    When the session ends, call save() to persist the complete conversation
    document to MongoDB.

    Args:
        session_id: Frontend-generated unique session identifier.
        user_id: Backend-generated user identifier.
    """

    def __init__(self, session_id: str, user_id: str, db: AsyncIOMotorDatabase):
        self.session_id = session_id
        self.user_id = user_id
        self.db = db
        self.connected_at = datetime.now(timezone.utc)
        self.started_at: datetime | None = None
        self.turns: list[dict] = []
        self.time_limit_seconds: int | None = None
        self.ended_reason: str | None = None

    def mark_started(self, time_limit_seconds: int | None = None):
        if self.started_at is None:
            self.started_at = datetime.now(timezone.utc)
        if time_limit_seconds is not None:
            self.time_limit_seconds = time_limit_seconds

    def mark_ended(self, reason: str | None = None, time_limit_seconds: int | None = None):
        if reason:
            self.ended_reason = reason
        if time_limit_seconds is not None:
            self.time_limit_seconds = time_limit_seconds

    def add_user_turn(self, text: str):
        if not text or not text.strip():
            return
        self.mark_started()
            
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
        self.mark_started()
        self.turns.append({
            "role": "agent",
            "text": text.strip(),
            "timestamp": datetime.now(timezone.utc),
        })

    async def save(self, confidence_data: dict | None = None, radar_data: dict | None = None, market_gap_data: dict | None = None, report_text: str | None = None):
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

        ended_at = datetime.now(timezone.utc)
        started_at = self.started_at or self.connected_at
        duration_seconds = int((ended_at - started_at).total_seconds())
        user_turn_count = sum(1 for t in self.turns if t["role"] == "user")
        agent_turn_count = sum(1 for t in self.turns if t["role"] == "agent")

        conversation_doc = {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": duration_seconds,
            "time_limit_seconds": self.time_limit_seconds,
            "ended_reason": self.ended_reason or "websocket_closed",
            "turn_count": len(self.turns),
            "user_turn_count": user_turn_count,
            "agent_turn_count": agent_turn_count,
            "turns": self.turns,
            "confidence_data": confidence_data,
            "radar_data": radar_data,
            "market_gap_data": market_gap_data,
            "report_text": report_text,
        }

        await self.db.conversations.insert_one(conversation_doc)
        logger.info(
            f"Conversation saved: session='{self.session_id}', "
            f"turns={len(self.turns)}, duration={duration_seconds}s"
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
