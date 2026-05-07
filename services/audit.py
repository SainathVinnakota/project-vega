"""Metadata-only audit logger. Raw prompts/responses are NOT logged."""
import logging

logger = logging.getLogger(__name__)


class MetadataOnlyAuditLogger:
    async def record(self, correlation_id: str, agent_id: str, version: str,
                     user_id: str, channel: str, status: str, model_id: str | None,
                     citation_count: int = 0, tool_count: int = 0):
        audit_event = {
            "correlation_id": correlation_id, "agent_id": agent_id, "agent_version": version,
            "user_id": user_id, "channel": channel, "status": status, "model_id": model_id,
            "citation_count": citation_count, "tool_count": tool_count,
            "raw_prompt_logged": False, "raw_response_logged": False,
        }
        logger.info("audit_event", extra=audit_event)
