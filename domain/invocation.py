"""Domain models: invocation request/response, citations, tool results."""
from pydantic import BaseModel, Field
from typing import Any, Literal


class AgentInvocationRequest(BaseModel):
    agent_id: str = ""
    input_text: str
    session_id: str | None = None
    channel: str = "api"
    request_metadata: dict[str, Any] = Field(default_factory=dict)


class SourceCitation(BaseModel):
    source_id: str
    title: str | None = None
    uri: str | None = None
    chunk_id: str | None = None
    score: float | None = None


class ToolResult(BaseModel):
    tool_id: str
    action_class: Literal["read"]
    status: Literal["success", "failed", "blocked"]
    result_summary: str | None = None
    error_code: str | None = None


class AgentInvocationResponse(BaseModel):
    status: Literal["success", "clarification_required", "blocked", "escalated", "error"]
    answer: str
    citations: list[SourceCitation] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    session_id: str
    correlation_id: str
    model_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
