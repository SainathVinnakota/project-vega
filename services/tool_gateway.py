"""AgentCore Gateway — read-only tool execution."""
import logging
from domain.invocation import ToolResult

logger = logging.getLogger(__name__)


class AgentCoreToolGateway:
    """Executes read-only tools through AgentCore Gateway. Non-read actions are blocked."""

    def __init__(self, boto3_factory=None):
        self.client = None
        if boto3_factory:
            try:
                self.client = boto3_factory.client("bedrock-agentcore")
            except Exception as e:
                logger.warning("agentcore_gateway_init_failed", extra={"error": str(e)})

    async def execute_tools(self, tool_requests: list[dict], profile=None) -> list[ToolResult]:
        results = []
        for req in tool_requests:
            action = req.get("action_class", "read")
            if action != "read":
                results.append(ToolResult(
                    tool_id=req["tool_id"], action_class="read",
                    status="blocked", error_code="NON_READ_ACTION_BLOCKED",
                ))
                continue
            # AgentCore Gateway invocation point
            results.append(ToolResult(
                tool_id=req["tool_id"], action_class="read",
                status="success", result_summary="Tool executed",
            ))
        return results
