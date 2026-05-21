# coaction_agent_platform/services/agent_service.py
"""Orchestration service: load profile → init agent → execute → return response."""

import os
import uuid
import structlog

from domain.models import (
    AgentInvocationRequest,
    AgentInvocationResponse,
    ExecutionProfile,
    ModelProfile,
    RetrievalProfile,
    MemoryProfile,
    IdentityContext,
)
from agents.underwriting_agent import UnderwritingAgent
from adapters.aws.dynamodb import DynamoDBAdapter

logger = structlog.get_logger(__name__)


class AgentService:
    """Central orchestrator for agent invocations.

    Responsibilities:
    1. Load ExecutionProfile for the requested agent_id
    2. Initialize/cache the UnderwritingAgent
    3. Load session history from DynamoDB
    4. Execute the query
    5. Save session state back to DynamoDB
    6. Return structured AgentInvocationResponse
    """

    def __init__(self, dynamodb: DynamoDBAdapter, region: str = "us-east-1"):
        self.dynamodb = dynamodb
        self.region = region
        self._agents: dict[str, UnderwritingAgent] = {}
        self._profiles: dict[str, ExecutionProfile] = {}

    def _load_profile(self, agent_id: str) -> ExecutionProfile:
        """Load an ExecutionProfile using the standard resolution chain.

        Resolution order (via ExecutionProfileRepository):
        1. In-memory cache
        2. DynamoDB (PROFILE#<agent_id> / VERSION#latest)
        3. Disk scan — all JSON files in profiles/ matched by agent_id field
        4. Environment variable fallback (safety net)
        """
        if agent_id in self._profiles:
            return self._profiles[agent_id]

        # Try ExecutionProfileRepository (DynamoDB → disk scan)
        try:
            from control_plane.execution_profile_repository import ExecutionProfileRepository

            repo = ExecutionProfileRepository(dynamodb_adapter=self.dynamodb, config_dir="profiles")
            # Use sync wrapper since _load_profile is called from sync context
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                # If we're in an async context, create a task
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    profile = loop.run_in_executor(
                        pool, lambda: asyncio.run(repo.get_profile(agent_id))
                    )
                    # Can't easily await here from sync, fall through to sync path
                    raise ValueError("Use sync path")
            except RuntimeError:
                # No running loop — safe to use asyncio.run
                profile = asyncio.run(repo.get_profile(agent_id))

            self._profiles[agent_id] = profile
            return profile
        except Exception as e:
            logger.debug("profile_repo_fallback", agent_id=agent_id, reason=str(e))

        # Fallback: try direct file load by filename
        profile = None
        import json
        from pathlib import Path

        profile_path = Path("profiles") / f"{agent_id}.json"
        if profile_path.exists():
            try:
                raw = json.loads(profile_path.read_text())
                profile = ExecutionProfile(**raw)
                logger.info(
                    "profile_loaded_from_file",
                    agent_id=agent_id,
                    path=str(profile_path),
                )
            except Exception as e:
                logger.warning(
                    "profile_file_parse_error",
                    path=str(profile_path),
                    error=str(e),
                )

        # Last resort: environment variables
        if not profile:
            kb_id_raw = os.getenv("BEDROCK_KB_ID", "2KMBSFAGGS")
            kb_ids = [kid.strip() for kid in kb_id_raw.split(",") if kid.strip()]
            model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")

            profile = ExecutionProfile(
                agent_id=agent_id,
                version="1.0",
                prompt_template_id="underwriting_system_v1",
                model_profile=ModelProfile(
                    model_id=model_id,
                    temperature=0.0,
                    max_tokens=4096,
                ),
                retrieval_profile=RetrievalProfile(
                    knowledge_base_ids=kb_ids,
                ),
                memory_profile=MemoryProfile(),
            )
            logger.warning(
                "using_default_profile",
                agent_id=agent_id,
                kb_ids=kb_ids,
                model_id=model_id,
                msg="No stored profile found; using env/defaults.",
            )

        self._profiles[agent_id] = profile
        return profile

    def _get_or_create_agent(self, agent_id: str) -> UnderwritingAgent:
        """Get or create a cached UnderwritingAgent."""
        if agent_id not in self._agents:
            profile = self._load_profile(agent_id)
            self._agents[agent_id] = UnderwritingAgent(profile=profile, region=self.region)
        return self._agents[agent_id]

    def reload_agent(self, agent_id: str) -> None:
        """Force reload an agent (e.g., after profile update)."""
        self._profiles.pop(agent_id, None)
        self._agents.pop(agent_id, None)
        logger.info("agent_reloaded", agent_id=agent_id)

    async def invoke(
        self,
        request: AgentInvocationRequest,
        identity: IdentityContext,
    ) -> AgentInvocationResponse:
        """Invoke an agent with the user's query.

        Full lifecycle:
        1. Load agent (with cached ExecutionProfile)
        2. Load session history from DynamoDB
        3. Execute the query
        4. Save updated session to DynamoDB
        5. Return structured response
        """
        agent_id = request.agent_id
        session_id = request.session_id or str(uuid.uuid4())
        user_id = identity.user_id
        role = identity.roles[0] if identity.roles else "agent"

        logger.info(
            "agent_invocation_start",
            agent_id=agent_id,
            session_id=session_id,
            user_id=user_id,
            role=role,
        )

        try:
            agent = self._get_or_create_agent(agent_id)

            # Load session history from DynamoDB
            history = []
            session_data = self.dynamodb.get_session(user_id, session_id)
            if session_data:
                history = session_data.get("messages", [])
                logger.info("session_history_loaded", count=len(history))

            # Extract model ID override from metadata
            model_id_override = request.request_metadata.get("model_id")

            # Execute the agent
            result = await agent.invoke(
                query=request.input_text,
                role=role,
                history=history,
                model_id=model_id_override,
            )

            # Build updated messages list for session persistence
            updated_messages = list(history)
            updated_messages.append({"role": "user", "content": request.input_text})

            # Persist citations alongside the answer so they survive session reloads.
            # The frontend's buildAssistantContent() only fires on live responses;
            # when a session is loaded from DynamoDB, citations must already be in the text.
            persisted_answer = result["answer"]
            citations = result.get("citations", [])
            if citations:
                persisted_answer += "\n\nSources:\n"
                for c in citations:
                    manual = getattr(c, "manual_name", None) or "Binding Authority Manual"
                    title = getattr(c, "title", None) or getattr(c, "source_id", "Source")
                    uri = getattr(c, "uri", None) or "#"
                    persisted_answer += f"\nSource Manual: {manual}\nSection: {title}\nLink: {uri}\n"

            updated_messages.append({"role": "assistant", "content": persisted_answer})

            # Generate session title from first user message
            title = (
                request.input_text[:80]
                if len(updated_messages) <= 2
                else (
                    session_data.get("title", request.input_text[:80])
                    if session_data
                    else request.input_text[:80]
                )
            )

            # Save session to DynamoDB
            self.dynamodb.save_session(
                user_id=user_id,
                session_id=session_id,
                title=title,
                messages=updated_messages,
            )

            return AgentInvocationResponse(
                status="success",
                answer=result["answer"],
                citations=result.get("citations", []),
                session_id=session_id,
                correlation_id=identity.correlation_id,
                model_id=model_id_override or agent.profile.model_profile.model_id,
                metadata={
                    "follow_up_questions": result.get("follow_up_questions", []),
                    "sources": result.get("sources", []),
                },
            )

        except Exception as e:
            logger.error(
                "agent_invocation_failed",
                agent_id=agent_id,
                error=str(e),
            )
            return AgentInvocationResponse(
                status="error",
                answer=f"An error occurred: {str(e)}",
                session_id=session_id,
                correlation_id=identity.correlation_id,
            )
