import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.agents.registry import AGENT_REGISTRY
from app.api.routes import admin, approvals, auth, requests
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.middleware import CorrelationIDMiddleware
from app.core.rate_limit import limiter
from app.hitl.gate import SENSITIVE_AGENT_TYPES
from app.models import (  # noqa: F401 -- register models with Base
    AuditLog,
    EnterpriseRequest,
    RagEvaluationRun,
    RolePermission,
    SubTask,
    SystemSetting,
    TraceSpan,
    User,
    WorkflowExecution,
)
from app.orchestrator.decomposer import (
    AGENT_KEYWORDS,
    FALLBACK_AGENT_TYPE,
    VALIDATION_AGENT_TYPE,
)
from app.rag.ingest import ingest_documents
from app.rbac.seed import seed_default_permissions

logger = logging.getLogger(__name__)

DEFAULT_JWT_SECRET = "change-me-in-production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Security: refuse to start with the default JWT secret in production.
    if settings.jwt_secret_key == DEFAULT_JWT_SECRET:
        if settings.is_production:
            raise RuntimeError(
                "JWT_SECRET_KEY is the default placeholder. "
                "Set a real random secret in backend/.env before deploying."
            )
        logger.warning(
            "=" * 70
            + "\nSECURITY WARNING: JWT_SECRET_KEY is the default placeholder.\n"
            "Set a real random secret in backend/.env before deploying.\n"
            + "=" * 70
        )

    # Sanity: catch decomposer/HITL typos at deploy time.
    referenced_agent_types = set(AGENT_KEYWORDS.keys())
    referenced_agent_types |= {FALLBACK_AGENT_TYPE, VALIDATION_AGENT_TYPE}
    referenced_agent_types |= set(SENSITIVE_AGENT_TYPES)
    unregistered = referenced_agent_types - set(AGENT_REGISTRY.keys())
    if unregistered:
        logger.warning(
            "CONFIG WARNING: agent type(s) referenced but not registered: %s",
            sorted(unregistered),
        )

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seeded = seed_default_permissions(db)
        if seeded:
            logger.info("Seeded %d default role permission(s).", seeded)
    finally:
        db.close()

    try:
        count = ingest_documents()
        logger.info("RAG knowledge base ready: %d document(s) ingested.", count)
    except Exception:
        logger.exception(
            "Could not ingest RAG documents on startup (is chromadb running?). "
            "The app will still start; RAG agent will error until this is fixed."
        )

    yield


app = FastAPI(title="Secure Autonomous Multi-Agent Enterprise Assistant", lifespan=lifespan)

# ── Rate limiting ─────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Correlation IDs ──────────────────────────────────────────────────────────
app.add_middleware(CorrelationIDMiddleware)

# ── CORS — specific methods/headers, not wildcard ────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

app.include_router(auth.router)
app.include_router(requests.router)
app.include_router(approvals.router)
app.include_router(admin.router)


@app.get("/api/health")
def health_check() -> dict:
    """Shallow liveness probe — checks DB and LLM connectivity."""
    from app.rag.llm import ollama_available

    db_ok = False
    try:
        import sqlalchemy
        _db = SessionLocal()
        _db.execute(sqlalchemy.text("SELECT 1"))
        _db.close()
        db_ok = True
    except Exception:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "unavailable",
        "llm": "ok" if ollama_available() else "unavailable",
    }
