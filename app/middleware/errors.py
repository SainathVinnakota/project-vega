"""
Error handling middleware.

Provides consistent error response formatting across all endpoints.
Catches unhandled exceptions and returns structured error responses.
"""

import logging
import traceback
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Global error handling middleware.

    Catches unhandled exceptions and returns structured error
    responses with correlation IDs for debugging.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            correlation_id = getattr(request.state, "correlation_id", "unknown")

            logger.error(
                "unhandled_exception",
                extra={
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                    "path": request.url.path,
                    "method": request.method,
                    "correlation_id": correlation_id,
                },
            )

            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "errors": [
                        {
                            "code": "INTERNAL_ERROR",
                            "message": "An internal error occurred.",
                        }
                    ],
                    "correlation_id": correlation_id,
                },
            )
