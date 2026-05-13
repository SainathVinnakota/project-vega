import json
import boto3
from abc import ABC, abstractmethod
from typing import Any, Dict
import httpx

class RuntimeHostAdapter(ABC):
    @abstractmethod
    async def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

class LocalFastApiRuntimeHost(RuntimeHostAdapter):
    """
    Adapter for a local FastAPI agent (typically for dev/test).
    Invokes the agent via HTTP.
    """
    def __init__(self, endpoint_url: str):
        self.endpoint_url = endpoint_url

    async def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.post(self.endpoint_url, json=payload)
            response.raise_for_status()
            return response.json()

class AgentCoreRuntimeHost(RuntimeHostAdapter):
    """
    Adapter for AWS Bedrock AgentCore Runtime.
    Invokes the agent via Boto3.
    """
    def __init__(self, agent_runtime_arn: str, region_name: str = "us-east-1"):
        self.agent_runtime_arn = agent_runtime_arn
        self.client = boto3.client("bedrock-agentcore", region_name=region_name)

    async def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        session_id = payload.get("session_id", "default-session-id")
        response = self.client.invoke_agent_runtime(
            agentRuntimeArn=self.agent_runtime_arn,
            runtimeSessionId=session_id,
            payload=json.dumps(payload).encode()
        )
        return json.loads(response["response"].read())
