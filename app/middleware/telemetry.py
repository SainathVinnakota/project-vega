"""
Telemetry middleware.

Captures request/response telemetry (latency, status codes) for
CloudWatch metrics emission.
"""

import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class TelemetryMiddleware(BaseHTTPMiddleware):
    """
    Middleware that captures request telemetry.

    Logs request latency, HTTP status code, method, and path
    for every request. Does NOT log request/response bodies.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000
        correlation_id = getattr(request.state, "correlation_id", "unknown")

        logger.info(
            "request_telemetry",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "correlation_id": correlation_id,
            },
        )

        response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 2))
        return response
