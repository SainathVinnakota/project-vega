"""Agent invocation router — POST /v1/agents/{agent_id}/invoke."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Any

from domain.invocation import AgentInvocationRequest, AgentInvocationResponse
from domain.identity import IdentityContext
from app.dependencies.identity import get_identity_context
from app.dependencies.services import get_orchestrator
from runtime.orchestrator import RuntimeOrchestrator

router = APIRouter(prefix="/v1/agents", tags=["agent-runtime"])


class InvokeRequest(BaseModel):
    """Invoke request body — for Postman / API testing."""
    input_text: str
    session_id: str | None = None
    user_id: str | None = None          # Override header-based user_id
    role: str | None = None             # Override header-based role (underwriter/agent)
    channel: str = "api"
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/{agent_id}/invoke", response_model=AgentInvocationResponse)
async def invoke_agent(
    agent_id: str,
    body: InvokeRequest,
    identity: IdentityContext = Depends(get_identity_context),
    orchestrator: RuntimeOrchestrator = Depends(get_orchestrator),
) -> AgentInvocationResponse:
    """Invoke an agent through the standard orchestration pipeline."""
    # Body values override header defaults for easier Postman testing
    if body.user_id:
        identity.user_id = body.user_id
    if body.role:
        identity.roles = [body.role]

    request = AgentInvocationRequest(
        agent_id=agent_id,
        input_text=body.input_text,
        session_id=body.session_id or identity.session_id,
        channel=body.channel,
        request_metadata=body.metadata,
    )
    return await orchestrator.execute(request, identity)


@router.get("/{agent_id}")
async def get_agent_info(agent_id: str):
    """Get agent metadata."""
    from app.dependencies.services import get_agent_registry
    registry = get_agent_registry()
    try:
        agent = registry.get_agent(agent_id)
        profile = registry.get_profile(agent_id)
        return {
            "agent_id": agent_id,
            "agent_type": agent.agent_type(),
            "version": profile.version,
            "memory_enabled": profile.memory_profile.enabled,
            "memory_id": profile.memory_profile.memory_id,
            "kb_ids": profile.retrieval_profile.knowledge_base_ids,
        }
    except ValueError:
        return {"error": f"Agent not found: {agent_id}"}


@router.get("/")
async def list_agents():
    """List all registered agents."""
    from app.dependencies.services import get_agent_registry
    return get_agent_registry().list_agents()
