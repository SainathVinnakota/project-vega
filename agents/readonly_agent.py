"""Read-only tool agent template — KB retrieval + read-only AgentCore Gateway tools."""
from runtime.strands_agent import StrandsBaseAgent


class ReadOnlyToolAgent(StrandsBaseAgent):
    """
    Read-only tool agent template.
    - Bedrock KB retrieval enabled
    - AgentCore Memory enabled
    - Read-only AgentCore Gateway tools enabled
    - Write/workflow/external actions blocked
    """

    def agent_type(self) -> str:
        return "readonly_tool_agent"
