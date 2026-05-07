"""
AgentCore entrypoint for Coaction Binding Authority Bot.
Uses BedrockAgentCoreApp for deployment to AgentCore Runtime.

This is the production entrypoint. Receives invoke payloads via AgentCore
runtime with the following fields:

  Required:
    prompt      — the user's question

  Optional:
    session_id  — for multi-turn conversation persistence
    user_id     — identifies the user (for memory scoping)
    role        — 'underwriter' or 'agent' (controls prompt behavior)

When AgentCore Memory is enabled (via .bedrock_agentcore.yaml memory config),
the agent automatically:
  - Reads long-term memory (user preferences, past insights) before answering
  - Writes user/assistant events after answering (short-term)
  - Long-term extraction happens asynchronously on the AWS side
"""
import os
import sys
import uuid

from dotenv import load_dotenv
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent

# Ensure project root is on path so imports work (we are in entrypoints/ folder)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

KNOWLEDGE_BASE_ID = os.environ.get("BEDROCK_KB_ID")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_CHAT_MODEL = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")
MODEL_PROVIDER = os.environ.get("MODEL_PROVIDER", "openai")
AGENTCORE_MEMORY_ID = os.environ.get("AGENTCORE_MEMORY_ID")

if KNOWLEDGE_BASE_ID:
    os.environ["KNOWLEDGE_BASE_ID"] = KNOWLEDGE_BASE_ID
os.environ["AWS_REGION"] = AWS_REGION


def _build_model():
    """Build the LLM model based on MODEL_PROVIDER."""
    provider = MODEL_PROVIDER.lower()
    if provider == "bedrock":
        from strands.models.bedrock import BedrockModel
        return BedrockModel(
            model_id=os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
            region_name=AWS_REGION,
            temperature=0,
            max_tokens=2048,
        )
    else:
        from strands.models.openai import OpenAIModel
        return OpenAIModel(
            client_args={"api_key": OPENAI_API_KEY},
            model_id=OPENAI_CHAT_MODEL,
            params={"temperature": 0, "max_tokens": 2048},
        )


def _get_model_id() -> str:
    if MODEL_PROVIDER.lower() == "bedrock":
        return os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")
    return OPENAI_CHAT_MODEL



def _get_memory_session_manager(session_id: str, user_id: str):
    """Build native AgentCoreMemorySessionManager for Strands."""
    if not AGENTCORE_MEMORY_ID:
        return None
    try:
        import boto3
        from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
        from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

        session = boto3.Session(region_name=AWS_REGION)
        config = AgentCoreMemoryConfig(
            memory_id=AGENTCORE_MEMORY_ID,
            session_id=session_id,
            actor_id=user_id,
        )
        return AgentCoreMemorySessionManager(
            agentcore_memory_config=config,
            region_name=AWS_REGION,
            boto_session=session
        )
    except Exception:
        return None


# ── Build agent components ──
from services.retrieval import search_manuals
from control_plane.prompt_repository import PromptRepository

prompt_repo = PromptRepository()
base_system_prompt = prompt_repo.get_template("coaction_binding_authority_bot")
model = _build_model()

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    """
    AgentCore invoke entrypoint.

    Payload:
      prompt     (str, required)  — the user's question
      session_id (str, optional)  — for multi-turn conversations
      user_id    (str, optional)  — user identity for memory scoping
      role       (str, optional)  — 'underwriter' or 'agent' (default: underwriter)
    """
    user_message = payload.get("prompt", "")
    session_id = payload.get("session_id", str(uuid.uuid4()))
    user_id = payload.get("user_id", "anonymous")
    role = payload.get("role", "underwriter")

    if not user_message:
        return {"status": "error", "error": "Missing required field: prompt"}
    if not KNOWLEDGE_BASE_ID:
        return {"status": "error", "error": "Missing required env var: BEDROCK_KB_ID"}
    if MODEL_PROVIDER.lower() == "openai" and not OPENAI_API_KEY:
        return {"status": "error", "error": "Missing required env var: OPENAI_API_KEY"}

    try:
        # Use native session manager for automatic memory handling
        session_manager = _get_memory_session_manager(session_id, user_id)

        # Configure native Bedrock Guardrails if available
        guardrail_config = None
        guardrail_id = os.environ.get("GUARDRAIL_ID")
        if guardrail_id:
            from strands.types.guardrails import GuardrailConfig
            guardrail_config = GuardrailConfig(
                guardrailIdentifier=guardrail_id,
                guardrailVersion=os.environ.get("GUARDRAIL_VERSION", "DRAFT"),
                trace="enabled"
            )

        # Create agent with native memory and guardrail integration
        agent = Agent(
            model=model,
            system_prompt=base_system_prompt,
            tools=[search_manuals],
            session_manager=session_manager,
            guardrail_config=guardrail_config,
        )

        # Invoke agent with the original query
        result = agent(user_message)
        answer = str(result)

        # Get retrieval sources
        from services.retrieval import get_last_retrieval_sources
        sources = get_last_retrieval_sources()
        source_urls = [s.get("url", "") for s in sources if s.get("url") and s["url"] != "N/A"]

        return {
            "status": "success",
            "answer": answer,
            "sources": source_urls[:5],
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "model_id": _get_model_id(),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "session_id": session_id,
        }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting AgentCore local server on http://127.0.0.1:{port}")
    print(f"Model: {MODEL_PROVIDER} / {_get_model_id()}")
    print(f"KB ID: {KNOWLEDGE_BASE_ID}")
    print(f"Memory: {'enabled (' + AGENTCORE_MEMORY_ID + ')' if AGENTCORE_MEMORY_ID else 'disabled'}")
    app.run(port=port)
