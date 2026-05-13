from typing import List, Optional, Literal, Any, Dict
from pydantic import BaseModel, Field

class ModelProfile(BaseModel):
    provider: Literal["bedrock", "openai"] = "bedrock"
    model_id: str
    temperature: float = 0.0
    max_tokens: int = 2048
    fallback_model_id: Optional[str] = None

class RetrievalProfile(BaseModel):
    provider: Literal["bedrock_knowledge_base"] = "bedrock_knowledge_base"
    enabled: bool = True
    knowledge_base_ids: List[str] = Field(default_factory=list)
    metadata_filters: Dict[str, Any] = Field(default_factory=dict)
    reranking_enabled: bool = True
    min_confidence: Optional[float] = None
    citations_required: bool = True

class MemoryProfile(BaseModel):
    provider: Literal["agentcore_memory"] = "agentcore_memory"
    enabled: bool = True
    memory_id: Optional[str] = None
    memory_scope: Literal["agent_user", "agent_session", "agent_task"] = "agent_user"
    retention_days: int = 90
    ltm_strategies: List[Literal["SEMANTIC", "SUMMARIZATION", "USER_PREFERENCE"]] = Field(default_factory=list)
    read_enabled: bool = True
    write_enabled: bool = True

class SessionProfile(BaseModel):
    provider: Literal["s3"] = "s3"
    bucket: Optional[str] = None
    prefix: str = "sessions/"
    conversation_window_size: int = 10

class ToolPermission(BaseModel):
    tool_id: str
    action_class: Literal["read"] = "read"
    allowed_roles: List[str] = Field(default_factory=list)
    requires_approval: bool = False

class GuardrailProfile(BaseModel):
    guardrail_id: Optional[str] = None
    guardrail_version: Optional[str] = "DRAFT"
    input_check_enabled: bool = True
    output_check_enabled: bool = True

class ObservabilityProfile(BaseModel):
    provider: Literal["cloudwatch"] = "cloudwatch"
    emit_metrics: bool = True
    emit_traces: bool = True
    log_raw_prompt: bool = False
    log_raw_response: bool = False

class ExecutionProfile(BaseModel):
    agent_id: str
    version: str = "1.0"
    orchestration_framework: Literal["strands"] = "strands"
    prompt_template_id: str
    model_profile: ModelProfile
    retrieval_profile: RetrievalProfile
    memory_profile: MemoryProfile
    session_profile: SessionProfile = Field(default_factory=SessionProfile)
    tool_permissions: List[ToolPermission] = Field(default_factory=list)
    guardrail_profile: GuardrailProfile
    observability_profile: ObservabilityProfile = ObservabilityProfile()
    response_contract_version: str = "v1"
