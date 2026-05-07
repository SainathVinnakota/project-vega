"""
Session manager — in-memory conversation state for local Strands agent use.

When AgentCore Memory is enabled, the orchestrator handles session persistence
via the memory provider (create_event / list_events). This session manager
serves as the local fallback for the Strands agent's internal follow-up
deduplication and within-request conversation tracking.
"""
from typing import Optional
import uuid
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class SessionManager:
    """
    In-memory session manager for local conversation tracking.

    The Strands agent uses this for:
      - Tracking messages within a request (for follow-up dedup)
      - Local dev when AgentCore Memory is not configured

    Persistent session storage is handled by AgentCore Memory
    at the orchestrator level.
    """

    def __init__(self):
        self._sessions: dict[str, dict] = {}
        logger.info("session_manager_initialized", extra={"mode": "in_memory"})

    def create_session(self, user_id: str = "anonymous", metadata: Optional[dict] = None) -> str:
        """Create a new session and return its ID."""
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        self._sessions[session_id] = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": now,
            "last_accessed": now,
            "messages": [],
            "metadata": metadata or {},
        }
        return session_id

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: str = "anonymous",
    ) -> None:
        """Add a message to session history."""
        now = datetime.utcnow()
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "session_id": session_id,
                "user_id": user_id,
                "created_at": now,
                "last_accessed": now,
                "messages": [],
                "metadata": {},
            }
        self._sessions[session_id]["messages"].append({
            "role": role,
            "content": content,
            "timestamp": now.isoformat(),
        })
        self._sessions[session_id]["last_accessed"] = now

    def get_messages(self, session_id: str) -> list[dict]:
        """Get session messages."""
        session = self._sessions.get(session_id)
        if session:
            session["last_accessed"] = datetime.utcnow()
            return session["messages"]
        return []

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get full session info."""
        return self._sessions.get(session_id)

    def clear_session(self, session_id: str) -> None:
        """Clear a session."""
        self._sessions.pop(session_id, None)
