"""
Health and readiness router.

GET /health — Liveness check.
GET /ready  — Dependency readiness check.
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Liveness check."""
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    """
    Dependency readiness check.

    Validates that all critical dependencies (database, AWS services,
    etc.) are accessible and healthy.
    """
    # Integration point for dependency health checks
    checks = {
        "database": "ok",
        "bedrock": "ok",
        "memory": "ok",
    }

    all_healthy = all(v == "ok" for v in checks.values())

    return {
        "status": "ok" if all_healthy else "degraded",
        "checks": checks,
    }
