"""Retrieval agent — the Coaction Binding Authority Bot."""
from runtime.strands_agent import StrandsBaseAgent


class RetrievalAgent(StrandsBaseAgent):
    """
    Coaction Binding Authority Bot (coaction_binding_authority_bot).

    This is the main underwriting assistant agent:
    - Uses Strands Agent with configurable LLM (OpenAI or Bedrock)
    - Retrieves from Bedrock Knowledge Base (GL + Property manuals)
    - Returns citations and follow-up questions
    - AgentCore Memory enabled when configured
    """

    def agent_type(self) -> str:
        return "retrieval_agent"
