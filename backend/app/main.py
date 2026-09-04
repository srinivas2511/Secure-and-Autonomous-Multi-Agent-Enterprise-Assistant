import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.registry import AGENT_REGISTRY
from app.api.routes import admin, approvals, auth, requests
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.hitl.gate import SENSITIVE_AGENT_TYPES
from app.models import (  # noqa: F401 -- register models with Base
    AuditLog,
    EnterpriseRequest,
    RagEvaluationRun,
    RolePermission,
    SubTask,
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
    # NFR-1: a default/well-known signing key lets anyone forge a valid JWT
    # for any user, including admin. Warn loudly rather than fail silently.
    if settings.jwt_secret_key == DEFAULT_JWT_SECRET:
        logger.warning(
            "=" * 70
            + "\nSECURITY WARNING: JWT_SECRET_KEY is still the default placeholder "
            "value.\nAnyone who knows this default (it's documented in "
            ".env.example) can forge\nvalid auth tokens for ANY user, including "
            "admin. Set a real random secret\nin backend/.env before this is "
            "anything but a local dev/demo instance.\n" + "=" * 70
        )

    # NFR-4: decomposer routing and HITL config reference agent types by
    # string; a typo there would otherwise fail silently until a real
    # request happened to hit it. Catch it loudly at deploy time instead.
    referenced_agent_types = set(AGENT_KEYWORDS.keys())
    referenced_agent_types |= {FALLBACK_AGENT_TYPE, VALIDATION_AGENT_TYPE}
    referenced_agent_types |= set(SENSITIVE_AGENT_TYPES)
    unregistered = referenced_agent_types - set(AGENT_REGISTRY.keys())
    if unregistered:
        logger.warning(
            "=" * 70
            + "\nCONFIG WARNING: the following agent type(s) are referenced by "
            "decomposer routing\nor HITL config but are NOT registered in "
            "AGENT_REGISTRY: %s\nRequests routed to them will fail at runtime. "
            "Check app/orchestrator/decomposer.py\nand app/hitl/gate.py "
            "against app/agents/registry.py.\n" + "=" * 70,
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
            "Could not ingest RAG documents on startup (is the chromadb service running?). "
            "The app will still start; the RAG agent will report errors until this is fixed."
        )

    yield


app = FastAPI(title="Secure Autonomous Multi-Agent Enterprise Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(requests.router)
app.include_router(approvals.router)
app.include_router(admin.router)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
