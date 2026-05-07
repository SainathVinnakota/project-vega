"""
Feedback router.

POST /v1/feedback — Capture user feedback.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Any

router = APIRouter(prefix="/v1/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    """User feedback request."""
    session_id: str
    correlation_id: str
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackResponse(BaseModel):
    """User feedback response."""
    status: str = "received"
    feedback_id: str | None = None


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """
    Capture user feedback.

    Records user satisfaction feedback for an agent interaction.
    """
    return FeedbackResponse(
        status="received",
        feedback_id=f"fb-{request.session_id[:8]}",
    )
