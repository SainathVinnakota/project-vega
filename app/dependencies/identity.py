"""Identity context dependency — parses API Gateway headers."""
import uuid
from fastapi import Header
from domain.identity import IdentityContext


async def get_identity_context(
    x_user_id: str = Header("anonymous", alias="X-User-Id"),
    x_roles: str = Header("underwriter", alias="X-Roles"),
    x_channel: str = Header("api", alias="X-Channel"),
    x_correlation_id: str = Header(None, alias="X-Correlation-Id"),
    x_session_id: str = Header(None, alias="X-Session-Id"),
) -> IdentityContext:
    return IdentityContext(
        user_id=x_user_id,
        roles=[r.strip() for r in x_roles.split(",") if r.strip()],
        channel=x_channel,
        correlation_id=x_correlation_id or str(uuid.uuid4()),
        session_id=x_session_id,
    )
