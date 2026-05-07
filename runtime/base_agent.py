"""
Base agent — abstract contract that ALL agents in the platform implement.

WHY THIS EXISTS:
─────────────────
This is NOT "unimplemented code". It's an abstract base class (ABC) — a contract.
Every agent (retrieval bot, tool bot, future bots) must implement these two methods.

HIERARCHY:
  BaseAgent (this file — defines the contract)
    └── StrandsBaseAgent (strands_agent.py — real Strands+OpenAI/Bedrock implementation)
          ├── RetrievalAgent (agents/retrieval_agent.py — e.g. coaction_binding_authority_bot)
          └── ReadOnlyToolAgent (agents/readonly_agent.py — future tool-based agents)

The old "BedrockKBAgent" logic now lives in StrandsBaseAgent.
RetrievalAgent extends it with zero extra code because the base already does everything.
"""
from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """Abstract base for all Coaction agents."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id

    @abstractmethod
    def agent_type(self) -> str:
        """Return agent type identifier (e.g. 'retrieval_agent', 'readonly_tool_agent')."""
        ...

    @abstractmethod
    async def invoke(self, query: str, session_id: str, role: str = "underwriter", **kwargs) -> dict:
        """
        Invoke the agent. Returns dict with:
          - answer: str
          - sources: list[str]
          - follow_up_questions: list[str]
          - model_id: str
          - session_id: str
        """
        ...
