import pytest
from services.authorization import AuthorizationService

@pytest.mark.asyncio
async def test_authorize_success():
    auth_service = AuthorizationService()
    # Should not raise any exception
    await auth_service.authorize(user_id="user123", roles=["admin"], agent_id="agent1")

@pytest.mark.asyncio
async def test_authorize_missing_user():
    auth_service = AuthorizationService()
    with pytest.raises(ValueError, match="Missing user identity"):
        await auth_service.authorize(user_id="", roles=["admin"], agent_id="agent1")
