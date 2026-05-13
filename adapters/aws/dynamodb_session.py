"""
DynamoDB session repository adapter.
Manages persistent stateless compute session snapshots in the vega-agent-sessions table.
"""

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

TABLE_NAME = "vega-agent-sessions"
DEFAULT_TTL_DAYS = 90


class DynamoDBSessionRepository:
    """
    Repository for persisting and restoring complete serialized session state
    snapshots using DynamoDB to support stateless container recovery.
    """

    def __init__(self, boto3_factory) -> None:
        self._table = boto3_factory.resource("dynamodb").Table(TABLE_NAME)

    async def get(self, session_id: str, agent_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve serialized session state snapshot from DynamoDB."""
        try:
            resp = self._table.get_item(Key={"session_id": session_id, "agent_id": agent_id})
            item = resp.get("Item")
            if not item:
                return None
            return {
                "session_id": item["session_id"],
                "agent_id": item["agent_id"],
                "user_id": item["user_id"],
                "state": json.loads(item.get("state", "{}")),
            }
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to fetch session snapshot from DynamoDB: {e}"
            )
            return None

    async def save(
        self,
        session_id: str,
        agent_id: str,
        user_id: str,
        state: dict,
        ttl_days: int = DEFAULT_TTL_DAYS,
    ) -> None:
        """Save a serialized session state snapshot to DynamoDB with auto-expiring TTL."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            self._table.put_item(
                Item={
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "user_id": user_id,
                    "state": json.dumps(state),
                    "updated_at": now,
                    "ttl": int(time.time()) + ttl_days * 86400,
                }
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to save session snapshot to DynamoDB: {e}"
            )

    async def delete(self, session_id: str, agent_id: str) -> None:
        """Delete a saved session state snapshot from DynamoDB."""
        try:
            self._table.delete_item(Key={"session_id": session_id, "agent_id": agent_id})
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to delete session snapshot from DynamoDB: {e}"
            )
