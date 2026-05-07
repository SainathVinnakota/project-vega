"""
AgentCore Memory provider — short-term + long-term persistent memory.

Uses the bedrock_agentcore.memory.MemoryClient SDK (NOT raw boto3).
Memory resources must be pre-created in the AWS console/CLI.
Each agent has its own memory_id in its ExecutionProfile.

SHORT-TERM MEMORY  (session-scoped)
  Stores raw conversational events (user/assistant messages) per session.
  Used to maintain multi-turn chat context within a session.

LONG-TERM MEMORY   (user-scoped, cross-session)
  Automatically extracts insights/preferences from short-term events
  via configured memory strategies (semantic, summarization) on the AWS side.
  Enables the agent to recall user context across sessions.
"""
import logging

from domain.invocation import AgentInvocationRequest, AgentInvocationResponse
from domain.identity import IdentityContext
from domain.execution_profile import ExecutionProfile

logger = logging.getLogger(__name__)


class AgentCoreMemoryProvider:
    """
    Reads and writes persistent memory via bedrock_agentcore.memory.MemoryClient.

    Uses the agent's ExecutionProfile to determine:
      - Whether memory is enabled
      - Which memory_id to use (per-agent)
      - Whether read/write are allowed

    This means each agent can have its own memory resource — no shared
    config, no new env vars when adding agents.
    """

    def __init__(self, boto3_session, region_name: str = "us-east-1") -> None:
        try:
            from bedrock_agentcore.memory import MemoryClient
            self.client = MemoryClient(
                region_name=region_name,
                boto3_session=boto3_session,
            )
            logger.info("agentcore_memory_client_initialized")
        except Exception as e:
            logger.warning("agentcore_memory_client_init_failed", extra={"error": str(e)})
            self.client = None

    # ─── Read: Long-Term (Semantic) ──────────────────────────────────

    async def read(
        self,
        request: AgentInvocationRequest,
        identity: IdentityContext,
        profile: ExecutionProfile,
    ) -> dict:
        """
        Read long-term (semantic) memory for the user.
        Returns a context dict for the agent to use.
        """
        mp = profile.memory_profile
        if not mp.enabled or not mp.read_enabled or not mp.memory_id or not self.client:
            return {}

        result = {}

        # Long-term: retrieve relevant memories for the user
        if request.input_text:
            long_term = await self._retrieve_long_term(
                memory_id=mp.memory_id,
                user_id=identity.user_id,
                query=request.input_text,
            )
            if long_term:
                result["long_term_context"] = long_term

        return result

    # ─── Write: Session Events ───────────────────────────────────────

    async def write(
        self,
        request: AgentInvocationRequest,
        response: AgentInvocationResponse,
        identity: IdentityContext,
        profile: ExecutionProfile,
    ) -> None:
        """
        Write user input and assistant response as session events.
        Long-term extraction happens asynchronously on the AgentCore side.
        """
        mp = profile.memory_profile
        if not mp.enabled or not mp.write_enabled or not mp.memory_id or not self.client:
            return

        session_id = request.session_id or response.session_id

        await self._add_event(
            memory_id=mp.memory_id,
            user_id=identity.user_id,
            session_id=session_id,
            user_msg=request.input_text,
            assistant_msg=response.answer,
        )

    # ─── Internal: Data Plane Operations ─────────────────────────────

    async def _add_event(
        self,
        memory_id: str,
        user_id: str,
        session_id: str,
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        """Write a conversation turn (user + assistant) as a single event."""
        try:
            self.client.create_event(
                memory_id=memory_id,
                actor_id=user_id,
                session_id=session_id,
                messages=[
                    (user_msg, "USER"),
                    (assistant_msg, "ASSISTANT"),
                ],
            )
            logger.debug("memory_event_created", extra={
                "memory_id": memory_id, "session_id": session_id,
                "user_id": user_id,
            })
        except Exception as e:
            logger.error("memory_event_create_failed", extra={
                "error": str(e), "session_id": session_id,
            })

    async def _retrieve_long_term(
        self,
        memory_id: str,
        user_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """Retrieve long-term memory records via semantic search."""
        try:
            records = self.client.retrieve_memories(
                memory_id=memory_id,
                namespace="/",  # Search all namespaces
                query=query,
                actor_id=user_id,
                top_k=top_k,
            )

            result = []
            for record in (records or []):
                content = record.get("content", record.get("text", ""))
                if content:
                    result.append({
                        "content": content,
                        "namespace": record.get("namespace", ""),
                        "score": record.get("score", 0.0),
                    })

            logger.info("memory_records_retrieved", extra={
                "user_id": user_id, "query": query[:50],
                "record_count": len(result),
            })
            return result

        except Exception as e:
            logger.error("memory_retrieve_failed", extra={
                "error": str(e), "user_id": user_id,
            })
            return []
