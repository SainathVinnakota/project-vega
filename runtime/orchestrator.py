"""
Runtime orchestrator — the standard execution pipeline.
Ties together authorization, guardrails, memory, agent invocation,
telemetry, and audit into a single flow.

Each agent's behavior is driven by its ExecutionProfile:
  - memory_profile → controls AgentCore Memory read/write
  - retrieval_profile → controls KB retrieval
  - guardrail_profile → controls input/output guardrails
  - model_profile → controls LLM selection
"""
import uuid
import logging

from domain.invocation import AgentInvocationRequest, AgentInvocationResponse, SourceCitation
from domain.identity import IdentityContext
from domain.execution_profile import ExecutionProfile
from control_plane.agent_registry import AgentRegistry
from services.authorization import AuthorizationService
from services.guardrails import GuardrailService
from services.memory import AgentCoreMemoryProvider
from services.telemetry import CloudWatchTelemetryEmitter
from services.audit import MetadataOnlyAuditLogger

logger = logging.getLogger(__name__)


class RuntimeOrchestrator:
    """Executes the standard agent invocation pipeline."""

    def __init__(
        self,
        agent_registry: AgentRegistry,
        authorization: AuthorizationService,
        guardrails: GuardrailService,
        memory: AgentCoreMemoryProvider,
        telemetry: CloudWatchTelemetryEmitter,
        audit: MetadataOnlyAuditLogger,
    ):
        self.registry = agent_registry
        self.authorization = authorization
        self.guardrails = guardrails
        self.memory = memory
        self.telemetry = telemetry
        self.audit = audit

    def _build_memory_context_prompt(self, memory_context: dict) -> str:
        """
        Build a context string from retrieved memory to inject into the agent.
        Combines long-term memory records with any relevant session history.
        """
        parts = []

        # Long-term memory: user preferences, past insights
        long_term = memory_context.get("long_term_context", [])
        if long_term:
            parts.append("=== Relevant context from past conversations ===")
            for record in long_term[:5]:  # Limit to top 5
                content = record.get("content", "")
                if content:
                    parts.append(f"- {content}")
            parts.append("")

        return "\n".join(parts)

    async def execute(
        self,
        request: AgentInvocationRequest,
        identity: IdentityContext,
    ) -> AgentInvocationResponse:
        """Execute the full invocation pipeline."""
        correlation_id = identity.correlation_id or str(uuid.uuid4())
        session_id = request.session_id or str(uuid.uuid4())
        # Ensure session_id is set on the request for downstream use
        request.session_id = session_id

        try:
            # 1. Resolve agent + profile
            agent = self.registry.get_agent(request.agent_id)
            profile = self.registry.get_profile(request.agent_id)

            # 2. Authorize
            await self.authorization.authorize(
                user_id=identity.user_id, roles=identity.roles, agent_id=request.agent_id,
            )

            # 3. Input guardrails
            await self.guardrails.check_input(request.input_text)

            # 4. Read memory (profile controls what gets read)
            memory_context = await self.memory.read(
                request=request,
                identity=identity,
                profile=profile,
            )

            # Build memory context string for the agent
            memory_prompt = self._build_memory_context_prompt(memory_context)

            # 5. Invoke agent
            role = identity.roles[0] if identity.roles else "underwriter"
            result = await agent.invoke(
                query=request.input_text,
                session_id=session_id,
                role=role,
                user_id=identity.user_id,
                memory_context=memory_prompt,
            )

            # 6. Output guardrails
            await self.guardrails.check_output(result["answer"])

            # 7. Build response
            citations = [
                SourceCitation(source_id=url, uri=url) for url in result.get("sources", [])
            ]
            response = AgentInvocationResponse(
                status="success",
                answer=result["answer"],
                citations=citations,
                follow_up_questions=result.get("follow_up_questions", []),
                session_id=session_id,
                correlation_id=correlation_id,
                model_id=result.get("model_id"),
            )

            # 8. Write memory (profile controls what gets written)
            await self.memory.write(
                request=request,
                response=response,
                identity=identity,
                profile=profile,
            )

            # 9. Telemetry & audit
            await self.telemetry.emit(
                agent_id=request.agent_id, status="success",
                model_id=result.get("model_id"), correlation_id=correlation_id,
                citation_count=len(citations),
            )
            await self.audit.record(
                correlation_id=correlation_id, agent_id=request.agent_id,
                version=profile.version, user_id=identity.user_id,
                channel=identity.channel, status="success",
                model_id=result.get("model_id"), citation_count=len(citations),
            )

            return response

        except Exception as e:
            logger.error("orchestrator_execute_failed", extra={"error": str(e), "agent_id": request.agent_id})
            return AgentInvocationResponse(
                status="error", answer=f"Error: {str(e)}",
                session_id=session_id, correlation_id=correlation_id,
            )
