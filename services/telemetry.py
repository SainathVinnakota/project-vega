"""Telemetry — CloudWatch metrics and structured logging."""
import logging

logger = logging.getLogger(__name__)


class CloudWatchTelemetryEmitter:
    def __init__(self, boto3_factory=None):
        self.client = None
        if boto3_factory:
            try:
                self.client = boto3_factory.client("cloudwatch")
            except Exception:
                pass

    async def emit(self, agent_id: str, status: str, model_id: str | None, correlation_id: str, **kwargs):
        data = {"agent_id": agent_id, "status": status, "model_id": model_id, "correlation_id": correlation_id, **kwargs}
        logger.info("telemetry", extra=data)
