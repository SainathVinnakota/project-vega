"""Agent registry — manages registered agents and their execution profiles."""
from runtime.base_agent import BaseAgent
from domain.execution_profile import ExecutionProfile


class AgentRegistry:
    """In-memory registry of agents and their execution profiles."""

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}
        self._profiles: dict[str, ExecutionProfile] = {}

    def register(self, agent: BaseAgent, profile: ExecutionProfile) -> None:
        """Register an agent with its execution profile."""
        self._agents[agent.agent_id] = agent
        self._profiles[agent.agent_id] = profile

    def get_agent(self, agent_id: str) -> BaseAgent:
        agent = self._agents.get(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")
        return agent

    def get_profile(self, agent_id: str) -> ExecutionProfile:
        profile = self._profiles.get(agent_id)
        if not profile:
            raise ValueError(f"Profile not found: {agent_id}")
        return profile

    def list_agents(self) -> list[dict]:
        return [
            {
                "agent_id": aid,
                "agent_type": a.agent_type(),
                "version": self._profiles[aid].version,
                "memory_enabled": self._profiles[aid].memory_profile.enabled,
            }
            for aid, a in self._agents.items()
        ]
