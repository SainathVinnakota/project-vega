"""Service dependency injection — wires up the runtime orchestrator."""
from functools import lru_cache

from control_plane.agent_registry import AgentRegistry
from agents.retrieval_agent import RetrievalAgent
from runtime.orchestrator import RuntimeOrchestrator
from services.authorization import AuthorizationService
from services.guardrails import GuardrailService
from services.memory import AgentCoreMemoryProvider
from services.telemetry import CloudWatchTelemetryEmitter
from services.audit import MetadataOnlyAuditLogger
from services.session_manager import SessionManager
from adapters.aws.boto3_factory import Boto3SessionFactory
from domain.execution_profile import (
    ExecutionProfile, ModelProfile, RetrievalProfile,
    MemoryProfile, GuardrailProfile, ObservabilityProfile,
)
from app.dependencies.settings import get_settings


@lru_cache()
def get_boto3_factory() -> Boto3SessionFactory:
    return Boto3SessionFactory(region_name=get_settings().aws_region)


@lru_cache()
def get_memory_provider() -> AgentCoreMemoryProvider:
    """Create the AgentCore Memory provider using MemoryClient SDK."""
    import boto3
    settings = get_settings()
    session = boto3.Session(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    return AgentCoreMemoryProvider(
        boto3_session=session,
        region_name=settings.aws_region,
    )


@lru_cache()
def get_session_manager() -> SessionManager:
    """Create the session manager (in-memory fallback for local dev)."""
    return SessionManager()


@lru_cache()
def get_agent_registry() -> AgentRegistry:
    settings = get_settings()
    registry = AgentRegistry()

    # ── Coaction Binding Authority Bot ──────────────────────────────
    binding_authority_bot = RetrievalAgent(
        agent_id="coaction_binding_authority_bot",
        prompt_template_id="coaction_binding_authority_bot",
    )

    binding_authority_profile = ExecutionProfile(
        agent_id="coaction_binding_authority_bot",
        version="v1",
        prompt_template_id="coaction_binding_authority_bot",
        model_profile=ModelProfile(
            provider="bedrock" if settings.model_provider.lower() == "bedrock" else "bedrock",
            model_id=(
                settings.bedrock_model_id
                if settings.model_provider.lower() == "bedrock"
                else settings.openai_chat_model
            ),
        ),
        retrieval_profile=RetrievalProfile(
            knowledge_base_ids=[settings.bedrock_kb_id] if settings.bedrock_kb_id else [],
        ),
        memory_profile=MemoryProfile(
            enabled=settings.agentcore_memory_enabled,
            memory_id=settings.agentcore_memory_id,
        ),
        guardrail_profile=GuardrailProfile(
            guardrail_id=settings.guardrail_id,
            guardrail_version=settings.guardrail_version,
        ),
        observability_profile=ObservabilityProfile(),
    )

    registry.register(binding_authority_bot, binding_authority_profile)

    # ── Future agents go here ──────────────────────────────────────
    # Example: Adding a new agent is just:
    #
    # claims_bot = RetrievalAgent(
    #     agent_id="claims_assistant_bot",
    #     prompt_template_id="claims_assistant",
    # )
    # claims_profile = ExecutionProfile(
    #     agent_id="claims_assistant_bot",
    #     version="v1",
    #     prompt_template_id="claims_assistant",
    #     model_profile=ModelProfile(model_id="..."),
    #     retrieval_profile=RetrievalProfile(knowledge_base_ids=["DIFFERENT_KB"]),
    #     memory_profile=MemoryProfile(memory_id="mem-different-id"),
    #     guardrail_profile=GuardrailProfile(),
    # )
    # registry.register(claims_bot, claims_profile)

    return registry


@lru_cache()
def get_orchestrator() -> RuntimeOrchestrator:
    return RuntimeOrchestrator(
        agent_registry=get_agent_registry(),
        authorization=AuthorizationService(),
        guardrails=GuardrailService(),
        memory=get_memory_provider(),
        telemetry=CloudWatchTelemetryEmitter(get_boto3_factory()),
        audit=MetadataOnlyAuditLogger(),
    )
