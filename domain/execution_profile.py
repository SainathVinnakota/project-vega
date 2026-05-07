"""
Execution profile domain models.

The execution profile is the runtime source of truth. It defines the model,
retrieval, memory, tool, guardrail, observability, and response contract used
for a specific agent version.
"""

from pydantic import BaseModel, Field
from typing import Any, Literal


class ModelProfile(BaseModel):
    """LLM model configuration for an agent."""
    provider: Literal["bedrock"] = "bedrock"
    model_id: str
    temperature: float = 0.0
    max_tokens: int | None = None
    fallback_model_id: str | None = None


class RetrievalProfile(BaseModel):
    """Knowledge-base retrieval configuration."""
    provider: Literal["bedrock_knowledge_base"] = "bedrock_knowledge_base"
    enabled: bool = True
    knowledge_base_ids: list[str]
    metadata_filters: dict[str, Any] = Field(default_factory=dict)
    reranking_enabled: bool = True
    min_confidence: float | None = None
    citations_required: bool = True


class MemoryProfile(BaseModel):
    """Persistent memory configuration."""
    provider: Literal["agentcore_memory"] = "agentcore_memory"
    enabled: bool = True
    memory_id: str | None = None  # AgentCore Memory resource ID (from AWS console)
    persistent: bool = True
    memory_scope: Literal["agent_user", "agent_session", "agent_task"] = "agent_user"
    retention_days: int = 90
    read_enabled: bool = True
    write_enabled: bool = True


class ToolPermission(BaseModel):
    """Permission entry for a single tool."""
    tool_id: str
    action_class: Literal["read"] = "read"
    allowed_roles: list[str] = Field(default_factory=list)
    requires_approval: bool = False


class GuardrailProfile(BaseModel):
    """Guardrail configuration for input/output checking."""
    guardrail_id: str | None = None
    guardrail_version: str | None = None
    input_check_enabled: bool = True
    output_check_enabled: bool = True


class ObservabilityProfile(BaseModel):
    """Telemetry and observability configuration."""
    provider: Literal["cloudwatch"] = "cloudwatch"
    emit_metrics: bool = True
    emit_traces: bool = True
    log_raw_prompt: bool = False
    log_raw_response: bool = False


class ExecutionProfile(BaseModel):
    """
    Complete execution profile for a specific agent version.

    This is the runtime source of truth that drives all behavior for
    model selection, retrieval, memory, tool permissions, guardrails,
    and observability.
    """
    agent_id: str
    version: str
    orchestration_framework: Literal["strands"] = "strands"
    prompt_template_id: str
    model_profile: ModelProfile
    retrieval_profile: RetrievalProfile
    memory_profile: MemoryProfile
    tool_permissions: list[ToolPermission] = Field(default_factory=list)
    guardrail_profile: GuardrailProfile
    observability_profile: ObservabilityProfile = ObservabilityProfile()
    response_contract_version: str = "v1"
