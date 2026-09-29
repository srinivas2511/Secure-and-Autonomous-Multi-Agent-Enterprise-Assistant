import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_sse, get_db
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.rate_limit import limiter
from app.models.enterprise_request import EnterpriseRequest
from app.models.user import User
from app.orchestrator.orchestrator import run_orchestration
from app.rag.llm import sanitize_input
from app.schemas.request import RequestCreate, RequestOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/requests", tags=["requests"])

# Shared executor for running blocking orchestration off the event loop.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="orchestrator")


def _orchestrate_in_thread(request_id: int) -> None:
    """Run orchestration in a thread with its own DB session."""
    db: Session = SessionLocal()
    try:
        req = db.query(EnterpriseRequest).filter(EnterpriseRequest.id == request_id).first()
        if req is None:
            logger.error("Background orchestration: request %d not found", request_id)
            return
        req.status = "processing"
        db.commit()
        run_orchestration(req, db)
    except Exception:
        logger.exception("Background orchestration failed for request %d", request_id)
        db.rollback()
        try:
            req = db.query(EnterpriseRequest).filter(EnterpriseRequest.id == request_id).first()
            if req:
                req.status = "failed"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.post("", response_model=RequestOut, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(f"{settings.rate_limit_requests_per_minute}/minute")
async def create_request(
    request: Request,
    payload: RequestCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EnterpriseRequest:
    # Enforce max length to prevent abuse.
    if len(payload.text) > settings.max_request_length:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Request text exceeds maximum length of {settings.max_request_length} characters.",
        )

    # Sanitize against prompt injection before persisting.
    clean_text = sanitize_input(payload.text.strip())

    enterprise_request = EnterpriseRequest(
        user_id=current_user.id, text=clean_text, status="processing"
    )
    db.add(enterprise_request)
    db.commit()
    db.refresh(enterprise_request)

    # Kick off orchestration in the background — returns 202 immediately.
    request_id = enterprise_request.id
    background_tasks.add_task(
        asyncio.get_event_loop().run_in_executor,
        _executor,
        _orchestrate_in_thread,
        request_id,
    )

    return enterprise_request


@router.get("/stream/{request_id}")
async def stream_request(
    request_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_sse),
    db: Session = Depends(get_db),
):
    """SSE endpoint: stream status updates for a request until it completes.

    Clients connect once and receive real-time agent progress without polling.
    """
    from sse_starlette.sse import EventSourceResponse
    import json as _json

    req = db.query(EnterpriseRequest).filter(EnterpriseRequest.id == request_id).first()
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if current_user.role != "admin" and req.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    async def event_generator():
        terminal_statuses = {"completed", "failed", "partially_denied"}
        prev_subtask_count = 0
        for _ in range(120):  # max 120 × 1 s = 2 min
            stream_db = SessionLocal()
            try:
                fresh = (
                    stream_db.query(EnterpriseRequest)
                    .filter(EnterpriseRequest.id == request_id)
                    .first()
                )
                if fresh is None:
                    break

                payload = {
                    "request_id": fresh.id,
                    "status": fresh.status,
                    "subtasks": [
                        {
                            "id": s.id,
                            "agent_type": s.agent_type,
                            "status": s.status,
                            "confidence": s.confidence,
                            "result": s.result,
                            "explanation": s.explanation,
                            "duration_ms": s.duration_ms,
                        }
                        for s in fresh.subtasks
                    ],
                }
                if len(fresh.subtasks) != prev_subtask_count or fresh.status in terminal_statuses:
                    prev_subtask_count = len(fresh.subtasks)
                    yield {"data": _json.dumps(payload)}

                if fresh.status in terminal_statuses:
                    break
            finally:
                stream_db.close()
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@router.get("", response_model=list[RequestOut])
def list_requests(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[EnterpriseRequest]:
    return (
        db.query(EnterpriseRequest)
        .filter(EnterpriseRequest.user_id == current_user.id)
        .order_by(EnterpriseRequest.created_at.desc())
        .offset(skip)
        .limit(min(limit, 100))
        .all()
    )


@router.get("/{request_id}", response_model=RequestOut)
def get_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EnterpriseRequest:
    query = db.query(EnterpriseRequest).filter(EnterpriseRequest.id == request_id)
    if current_user.role != "admin":
        query = query.filter(EnterpriseRequest.user_id == current_user.id)
    req = query.first()
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return req
