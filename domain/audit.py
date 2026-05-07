"""
Audit domain models.

Defines the audit event structure for metadata-only audit logging.
Raw prompts and raw responses are NOT logged by default.
"""

from pydantic import BaseModel, Field
from typing import Any


class AuditEvent(BaseModel):
    """Metadata-only audit event. No raw prompts or responses."""
    correlation_id: str
    agent_id: str
    agent_version: str
    user_id: str
    channel: str
    status: str
    model_id: str | None = None
    citation_count: int = 0
    tool_count: int = 0
    raw_prompt_logged: bool = False
    raw_response_logged: bool = False
    additional_metadata: dict[str, Any] = Field(default_factory=dict)
