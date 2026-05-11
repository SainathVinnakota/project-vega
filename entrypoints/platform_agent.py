"""
AgentCore entrypoint using the fully configurable Platform Orchestrator.
This complies with the HLD by delegating execution to the RuntimeOrchestrator.
"""
import os
import sys
import uuid
import asyncio
import logging

from dotenv import load_dotenv
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Ensure project root is on path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from domain.invocation import AgentInvocationRequest
from domain.identity import IdentityContext
from app.dependencies.services import get_orchestrator
from app.dependencies.settings import get_settings

logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

# ── AgentCore Identity: API Key Resolution ───────────────────────────
# The WorkloadAccessToken header is only present for OAuth-based auth
# flows, NOT for SigV4 invocations (which agentcore invoke uses).
# We use a two-tier approach:
#   1. Check if OPENAI_API_KEY was passed directly via -env flag
#   2. If not, try the Identity service with a self-created workload identity
_api_key_resolved = False

def _resolve_api_key_if_needed():
    """Ensure the OpenAI API key is available before the orchestrator runs."""
    global _api_key_resolved
    if _api_key_resolved:
        return

    settings = get_settings()

    # Already available (from -env flag or .env file)
    if settings.openai_api_key:
        _api_key_resolved = True
        return

    provider_name = os.environ.get("BEDROCK_AGENTCORE_MODEL_PROVIDER_API_KEY_NAME")
    if not provider_name:
        _api_key_resolved = True
        return

    try:
        from bedrock_agentcore.runtime.context import BedrockAgentCoreContext
        from bedrock_agentcore.services.identity import IdentityClient

        region = os.environ.get("AWS_REGION", "us-east-1")
        client = IdentityClient(region)

        # Try the request-scoped workload token first (OAuth flows)
        workload_token = BedrockAgentCoreContext.get_workload_access_token()

        if not workload_token:
            # SigV4 flow: create our own workload identity to get a token
            logger.info("No request workload token — creating workload identity for API key fetch")
            try:
                wi = client.create_workload_identity()
                token_resp = client.get_workload_access_token(wi["name"])
                workload_token = token_resp["workloadAccessToken"]
            except Exception as wi_err:
                logger.error("Failed to create workload identity: %s", wi_err)
                return

        api_key = asyncio.run(client.get_api_key(
            provider_name=provider_name,
            agent_identity_token=workload_token,
        ))

        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
            settings.openai_api_key = api_key
            logger.info("✅ API key resolved from AgentCore Identity (provider: %s)", provider_name)
            _api_key_resolved = True
        else:
            logger.warning("Identity returned empty API key for provider: %s", provider_name)

    except Exception as e:
        logger.error("Failed to resolve API key from Identity: %s", e)


@app.entrypoint
def invoke(payload: dict) -> dict:
    # Resolve API key from AgentCore Identity (first request only)
    _resolve_api_key_if_needed()

    user_message = payload.get("prompt", "")
    session_id = payload.get("session_id", str(uuid.uuid4()))
    user_id = payload.get("user_id", "anonymous")
    role = payload.get("role", "underwriter")
    agent_id = payload.get("agent_id", "coaction_binding_authority_bot")
    channel = payload.get("channel", "agentcore")
    correlation_id = payload.get("correlation_id", str(uuid.uuid4()))

    if not user_message:
        return {"status": "error", "error": "Missing required field: prompt"}

    # Build the standard domain objects expected by the Orchestrator
    request = AgentInvocationRequest(
        agent_id=agent_id,
        input_text=user_message,
        session_id=session_id,
        channel=channel,
        request_metadata=payload,
    )

    identity = IdentityContext(
        user_id=user_id,
        roles=[role],
        channel=channel,
        correlation_id=correlation_id,
        session_id=session_id,
    )

    # Get orchestrator from dependency injection
    orchestrator = get_orchestrator()

    try:
        # Execute the full configurable pipeline (Auth, Guardrails, Memory, Retrieval, LLM, Telemetry)
        response = asyncio.run(orchestrator.execute(request, identity))

        # Map back to AgentCore expected response format
        return {
            "status": response.status,
            "answer": response.answer,
            "sources": [c.uri for c in response.citations if c.uri],
            "session_id": response.session_id,
            "user_id": user_id,
            "role": role,
            "model_id": response.model_id,
            "correlation_id": response.correlation_id,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "session_id": session_id,
            "correlation_id": correlation_id,
        }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting Platform AgentCore server on http://127.0.0.1:{port}")
    app.run(port=port)
