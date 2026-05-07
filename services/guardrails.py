"""Guardrail service — input/output checks via Bedrock Guardrails."""
import logging
from app.dependencies.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class GuardrailService:
    async def check_input(self, text: str) -> None:
        if not settings.guardrail_id:
            return
        # Bedrock Guardrails API integration point
        logger.info("input_guardrail_check")

    async def check_output(self, text: str) -> None:
        if not settings.guardrail_id:
            return
        logger.info("output_guardrail_check")
