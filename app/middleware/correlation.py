"""
Correlation ID middleware.

Ensures every request has a correlation ID for end-to-end tracing.
If X-Correlation-Id is not provided in the request headers, a new
UUID is generated.
"""

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that ensures every request has a correlation ID.

    Reads X-Correlation-Id from request headers. If not present,
    generates a new UUID. Adds the correlation ID to the response
    headers for end-to-end tracing.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = request.headers.get("X-Correlation-Id")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Store in request state for downstream access
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers["X-Correlation-Id"] = correlation_id
        return response
