"""
Strands base agent — the REAL working agent implementation.

This is where the old "BedrockKBAgent" logic now lives.
It creates a Strands Agent with a configurable LLM model (OpenAI or Bedrock),
wires in the search_manuals KB retrieval tool, manages conversation history,
extracts follow-up questions, and deduplicates them.

MODEL CONFIGURATION:
  Set MODEL_PROVIDER in .env to choose the LLM backend:
    MODEL_PROVIDER=openai    → Uses OpenAI (GPT-4o, etc.)
    MODEL_PROVIDER=bedrock   → Uses Amazon Bedrock (Claude, etc.)

  The model ID is set via:
    OPENAI_CHAT_MODEL=gpt-4o           (when provider=openai)
    BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0  (when provider=bedrock)

MEMORY INTEGRATION:
  When AgentCore Memory is enabled, session history is managed through
  the AgentCoreMemoryProvider. When disabled, falls back to in-memory
  session management.
"""
import re
from typing import Optional
from strands import Agent
from runtime.base_agent import BaseAgent
from services.retrieval import search_manuals, get_last_retrieval_sources
from services.session_manager import SessionManager
from control_plane.prompt_repository import PromptRepository
from app.dependencies.settings import get_settings
from app.core.logger import get_logger
import boto3
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
from strands.types.guardrails import GuardrailConfig

logger = get_logger(__name__)
settings = get_settings()


def _build_model():
    """
    Build the LLM model based on MODEL_PROVIDER setting.
    Supports: 'openai' (default), 'bedrock'.
    """
    provider = settings.model_provider.lower()

    if provider == "bedrock":
        from strands.models.bedrock import BedrockModel
        model = BedrockModel(
            model_id=settings.bedrock_model_id,
            region_name=settings.aws_region,
            temperature=0,
            max_tokens=2048,
        )
        logger.info("model_initialized", provider="bedrock", model_id=settings.bedrock_model_id)
        return model

    else:  # openai (default)
        from strands.models.openai import OpenAIModel
        model = OpenAIModel(
            client_args={"api_key": settings.openai_api_key},
            model_id=settings.openai_chat_model,
            params={"temperature": 0, "max_tokens": 2048},
        )
        logger.info("model_initialized", provider="openai", model_id=settings.openai_chat_model)
        return model


def _get_active_model_id() -> str:
    """Return the model ID string for the currently configured provider."""
    if settings.model_provider.lower() == "bedrock":
        return settings.bedrock_model_id
    return settings.openai_chat_model


def _normalize_question(text: str) -> str:
    if not text:
        return ""
    normalized = text.strip().lower()
    normalized = re.sub(r"^\d+\.\s*", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[^\w\s]", "", normalized)
    return normalized


def _extract_followups_from_assistant(content: str) -> list[str]:
    if not content or "**You might also want to ask:**" not in content:
        return []
    section = content.split("**You might also want to ask:**", 1)[1]
    return [m.strip() for m in re.findall(r"\d+\.\s*(.+)", section) if m.strip()]


class StrandsBaseAgent(BaseAgent):
    """
    Working Strands-based agent with configurable LLM and Bedrock KB retrieval.

    This is the core agent class. The old BedrockKBAgent's logic is here:
    - Creates Strands Agent with OpenAI or Bedrock model
    - Wires in the search_manuals tool (which queries Bedrock Knowledge Base using BEDROCK_KB_ID)
    - Manages conversation history via SessionManager (backed by AgentCore Memory or local)
    - Extracts and deduplicates follow-up questions
    - Accepts long-term memory context from the orchestrator
    """

    def __init__(self, agent_id: str, prompt_template_id: str = "coaction_binding_authority_bot"):
        super().__init__(agent_id)
        self.prompt_repo = PromptRepository()
        self.prompt_template_id = prompt_template_id
        # SessionManager is injected later via set_session_manager() or uses a default
        self._session_manager = None
        self._agents: dict[tuple[str, str], Agent] = {}

    @property
    def session_manager(self) -> SessionManager:
        """Lazy-initialize a default SessionManager if none was injected."""
        if self._session_manager is None:
            self._session_manager = SessionManager()
        return self._session_manager

    def set_session_manager(self, sm: SessionManager) -> None:
        """Inject a SessionManager (optionally backed by AgentCore Memory)."""
        self._session_manager = sm

    def agent_type(self) -> str:
        return "strands_agent"

    def _get_memory_session_manager(self, session_id: str, user_id: str) -> Optional[AgentCoreMemorySessionManager]:
        """Build native AgentCoreMemorySessionManager for Strands."""
        if not settings.agentcore_memory_enabled or not settings.agentcore_memory_id:
            return None

        try:
            session = boto3.Session(
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region,
            )

            config = AgentCoreMemoryConfig(
                memory_id=settings.agentcore_memory_id,
                session_id=session_id,
                actor_id=user_id,
            )
            
            return AgentCoreMemorySessionManager(
                agentcore_memory_config=config,
                region_name=settings.aws_region,
                boto_session=session
            )
        except Exception as e:
            logger.warning("native_memory_init_failed", error=str(e))
            return None

    def _get_s3_session_manager(self, session_id: str):
        """Build native S3SessionManager for Strands fallback."""
        if not settings.s3_bucket_name:
            return None
        
        try:
            from strands.session.s3_session_manager import S3SessionManager
            session = boto3.Session(
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region,
            )
            return S3SessionManager(
                session_id=session_id,
                bucket=settings.s3_bucket_name,
                prefix="sessions/",
                boto_session=session
            )
        except Exception as e:
            logger.warning("s3_session_manager_init_failed", error=str(e))
            return None

    def _get_or_create_agent(self, session_id: str, role: str, user_id: str = "anonymous") -> Agent:
        """Get cached agent or create new one for this session+role combo."""
        role_key = (role or "").strip().lower()
        cache_key = (session_id, role_key)

        if cache_key not in self._agents:
            model = _build_model()
            prompt = self.prompt_repo.get_template(self.prompt_template_id)
            
            # 1. Try native AgentCore Memory session manager
            session_manager = self._get_memory_session_manager(session_id, user_id)
            
            # 2. Fallback to S3 session manager if memory is disabled but S3 is available
            if session_manager is None:
                session_manager = self._get_s3_session_manager(session_id)
            
            # Configure native Bedrock Guardrails if available
            guardrail_config = None
            if settings.guardrail_id:
                guardrail_config = GuardrailConfig(
                    guardrailIdentifier=settings.guardrail_id,
                    guardrailVersion=settings.guardrail_version or "DRAFT",
                    trace="enabled"
                )
            
            self._agents[cache_key] = Agent(
                model=model,
                system_prompt=prompt,
                tools=[search_manuals],
                session_manager=session_manager,
                guardrail_config=guardrail_config,
            )
            logger.info("agent_created",
                        agent_id=self.agent_id,
                        session_id=session_id,
                        model_provider=settings.model_provider,
                        model_id=_get_active_model_id(),
                        kb_id=settings.bedrock_kb_id,
                        memory_enabled=session_manager is not None,
                        guardrails_enabled=guardrail_config is not None)

        return self._agents[cache_key]

    async def invoke(self, query: str, session_id: str, role: str = "underwriter", **kwargs) -> dict:
        """
        Full agent invocation flow with native memory management.
        """
        user_id = kwargs.get("user_id", "anonymous")

        # Get/create agent (handles native memory integration internally)
        agent = self._get_or_create_agent(session_id, role, user_id=user_id)

        # Execute Strands agent with original query
        # History and long-term context are handled by session_manager
        response = agent(query)
        answer = str(response)

        # Extract follow-up questions from the answer
        follow_up_questions = []
        fu_marker = "**You might also want to ask:**"
        if fu_marker in answer:
            parts = answer.split(fu_marker)
            answer = parts[0].strip()
            raw_followups = [m.strip() for m in re.findall(r"\d+\.\s*(.+)", parts[1]) if m.strip()]

            # Dedup against conversation history
            history = self.session_manager.get_messages(session_id)
            historical_questions = set()
            for msg in history:
                r = (msg.get("role") or "").strip().lower()
                c = msg.get("content") or ""
                if r == "user":
                    nq = _normalize_question(c)
                    if nq:
                        historical_questions.add(nq)
                elif r == "assistant":
                    for prev_fu in _extract_followups_from_assistant(c):
                        nfu = _normalize_question(prev_fu)
                        if nfu:
                            historical_questions.add(nfu)

            seen = set()
            for q in raw_followups:
                nq = _normalize_question(q)
                if not nq or nq in historical_questions or nq in seen:
                    continue
                seen.add(nq)
                follow_up_questions.append(q)
                if len(follow_up_questions) == 3:
                    break

        # Get sources from the last retrieval
        retrieval_sources = get_last_retrieval_sources()
        all_urls = [s["url"] for s in retrieval_sources if s.get("url") and s["url"] != "N/A"]
        cited_urls = [url for url in all_urls if url in answer]
        sources = cited_urls if cited_urls else all_urls[:3]

        return {
            "answer": answer,
            "sources": sources,
            "follow_up_questions": follow_up_questions,
            "model_id": _get_active_model_id(),
            "session_id": session_id,
        }
