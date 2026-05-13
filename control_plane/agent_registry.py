"""Agent registry — manages registered agents and their execution profiles."""
import os
import json
from typing import Optional
from runtime.base_agent import BaseAgent
from domain.execution_profile import ExecutionProfile


class AgentRegistry:
    """In-memory registry of agents and their execution profiles."""

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}
        self._profiles: dict[str, ExecutionProfile] = {}

    def _auto_load(self, agent_id: str) -> bool:
        """Attempt to load agent configuration dynamically from profiles directory."""
        path = os.path.join("profiles", f"{agent_id}.json")
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Map top-level nested structures dynamically if present
            profile = ExecutionProfile(**data)
            
            # Create a generic RetrievalAgent implementation for standard execution profiles
            from agents.retrieval_agent import RetrievalAgent
            agent = RetrievalAgent(
                agent_id=agent_id,
                prompt_template_id=profile.prompt_template_id or agent_id,
            )
            self.register(agent, profile)
            return True
        except Exception:
            return False

    def register(self, agent: BaseAgent, profile: ExecutionProfile) -> None:
        """Register an agent with its execution profile."""
        self._agents[agent.agent_id] = agent
        self._profiles[agent.agent_id] = profile

    def get_agent(self, agent_id: str) -> BaseAgent:
        if agent_id not in self._agents:
            if not self._auto_load(agent_id):
                raise ValueError(f"Agent not found: {agent_id}")
        return self._agents[agent_id]

    def get_profile(self, agent_id: str) -> ExecutionProfile:
        if agent_id not in self._profiles:
            if not self._auto_load(agent_id):
                raise ValueError(f"Profile not found: {agent_id}")
        return self._profiles[agent_id]

    def list_agents(self) -> list[dict]:
        # Pre-scan profiles folder to reflect fully discovered JSON files
        if os.path.exists("profiles"):
            for fname in os.listdir("profiles"):
                if fname.endswith(".json"):
                    aid = fname[:-5]
                    if aid not in self._agents:
                        self._auto_load(aid)

        return [
            {
                "agent_id": aid,
                "agent_type": a.agent_type(),
                "version": self._profiles[aid].version,
                "memory_enabled": self._profiles[aid].memory_profile.enabled,
            }
            for aid, a in self._agents.items()
        ]
