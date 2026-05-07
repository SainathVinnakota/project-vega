"""
Identity context domain model.

Represents the authenticated caller identity propagated from the API Gateway
through the FastAPI layer. Primary authentication terminates at API Gateway;
the runtime consumes trusted identity context from gateway headers.
"""

from pydantic import BaseModel, Field
from typing import Any


class IdentityContext(BaseModel):
    """Validated identity context parsed from API Gateway headers."""
    user_id: str
    roles: list[str] = Field(default_factory=list)
    channel: str
    application_id: str | None = None
    session_id: str | None = None
    correlation_id: str
    claims: dict[str, Any] = Field(default_factory=dict)
