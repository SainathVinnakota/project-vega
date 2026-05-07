"""Agent template factory — creates agents by type."""
from agents.retrieval_agent import RetrievalAgent
from agents.readonly_agent import ReadOnlyToolAgent

AGENT_TEMPLATES = {
    "retrieval_agent": RetrievalAgent,
    "readonly_tool_agent": ReadOnlyToolAgent,
}


def create_agent(agent_type: str, agent_id: str, prompt_template_id: str = "underwriting_agent"):
    cls = AGENT_TEMPLATES.get(agent_type)
    if not cls:
        raise ValueError(f"Unknown agent type: {agent_type}. Available: {list(AGENT_TEMPLATES.keys())}")
    return cls(agent_id=agent_id, prompt_template_id=prompt_template_id)
