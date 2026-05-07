"""
Coaction Agent Platform — FastAPI Entry Point.
Registers all routers, middleware, and initializes the agent registry on startup.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logger import setup_logging, get_logger
from app.db.database import engine
from app.db.models import Base

# Routers
from app.routers.invoke import router as invoke_router
from app.routers.sessions import router as session_router
from app.routers.feedback import router as feedback_router
from app.routers.health import router as health_router
from app.routers.auth import router as auth_router

# Middleware
from app.middleware.correlation import CorrelationIdMiddleware
from app.middleware.telemetry import TelemetryMiddleware
from app.middleware.errors import ErrorHandlingMiddleware

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("startup", service="coaction-agent-platform")

    # Create DB tables
    Base.metadata.create_all(bind=engine)

    # Initialize agent registry (triggers agent creation)
    from app.dependencies.services import get_agent_registry
    registry = get_agent_registry()
    agents = registry.list_agents()
    logger.info("agents_registered", count=len(agents), agents=[a["agent_id"] for a in agents])

    # Log per-agent memory status
    for agent_info in agents:
        aid = agent_info["agent_id"]
        profile = registry.get_profile(aid)
        mp = profile.memory_profile
        if mp.enabled and mp.memory_id:
            logger.info("agent_memory_ready", agent_id=aid, memory_id=mp.memory_id)
        elif mp.enabled and not mp.memory_id:
            logger.warning("agent_memory_no_id", agent_id=aid,
                           msg="memory enabled but AGENTCORE_MEMORY_ID not set")
        else:
            logger.info("agent_memory_disabled", agent_id=aid)

    logger.info("ready", platform_version="1.0.0")
    yield
    logger.info("shutdown", service="coaction-agent-platform")


app = FastAPI(
    title="Coaction Agent Platform",
    description="Standard agent runtime — Project Vega architecture",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Middleware (outermost first) ──
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(TelemetryMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──
app.include_router(invoke_router)
app.include_router(session_router)
app.include_router(feedback_router)
app.include_router(health_router)
app.include_router(auth_router)
