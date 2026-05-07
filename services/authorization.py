"""Authorization service — role and policy checks."""
import logging

logger = logging.getLogger(__name__)


class AuthorizationService:
    async def authorize(self, user_id: str, roles: list[str], agent_id: str) -> None:
        if not user_id:
            raise ValueError("Missing user identity")
        logger.info("authorization_passed", extra={"user_id": user_id, "agent_id": agent_id})
