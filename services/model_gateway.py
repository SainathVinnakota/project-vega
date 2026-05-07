"""Bedrock model gateway — LLM invocation via Strands Agent."""
import logging

logger = logging.getLogger(__name__)


class BedrockModelGateway:
    """Wraps the Strands Agent invocation as the model gateway."""

    def __init__(self, boto3_factory=None):
        pass  # Strands Agent handles model invocation internally

    async def invoke(self, agent, query: str) -> str:
        """Invoke the Strands agent and return the raw response text."""
        try:
            response = agent(query)
            return str(response)
        except Exception as e:
            logger.error("model_invocation_failed", extra={"error": str(e)})
            raise
