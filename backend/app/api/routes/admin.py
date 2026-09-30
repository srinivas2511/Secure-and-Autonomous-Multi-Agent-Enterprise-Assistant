from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload

from app.agents.registry import AGENT_REGISTRY
from app.api.deps import get_current_user, get_db
from app.audit.logger import log_event
from app.core.settings_store import get_all_settings, get_hitl_threshold, set_hitl_threshold
from app.hitl.gate import SENSITIVE_AGENT_TYPES
from app.metrics.evaluator import compute_metrics
from app.models.audit_log import AuditLog
from app.models.enterprise_request import EnterpriseRequest
from app.models.rag_evaluation_run import RagEvaluationRun
from app.models.role_permission import RolePermission
from app.models.sub_task import SubTask
from app.models.trace_span import TraceSpan
from app.models.user import User
from app.rag.evaluation import run_evaluation
from app.rbac.roles import VALID_ROLES, get_agent_types, require_admin
from app.schemas.admin import (
    AuditLogOut,
    PermissionsMatrixOut,
    PermissionToggleRequest,
    UserAdminOut,
    UserUpdateRequest,
)
from app.schemas.metrics import EvaluationReport
from app.schemas.rag_evaluation import RagEvaluationRunOut
from app.schemas.trace import DecisionTraceOut, TraceRequestContext
from app.schemas.trace_span import TraceSpanOut

router = APIRouter(prefix="/api/admin", tags=["admin"])

DEFAULT_AUDIT_LOG_LIMIT = 100
MAX_AUDIT_LOG_LIMIT = 500


class AdminRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: int
    user_id: int
    requester_email: str
    text: str
    status: str
    subtask_count: int
    created_at: datetime
    completed_at: datetime | None


def _build_matrix(db: Session) -> PermissionsMatrixOut:
    rows = db.query(RolePermission).all()
    matrix: dict[str, list[str]] = {role: [] for role in sorted(VALID_ROLES)}
    for row in rows:
        matrix.setdefault(row.role, []).append(row.agent_type)
    for role in matrix:
        matrix[role].sort()
    return PermissionsMatrixOut(
        roles=sorted(VALID_ROLES), agent_types=sorted(get_agent_types()), matrix=matrix
    )


@router.get("/requests", response_model=list[AdminRequestOut])
def list_all_requests(
    skip: int = 0,
    limit: int = Query(default=50, le=200, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AdminRequestOut]:
    """Admin view: all requests across all users, newest first (paginated)."""
    require_admin(current_user)
    rows = (
        db.query(EnterpriseRequest)
        .options(joinedload(EnterpriseRequest.user), joinedload(EnterpriseRequest.subtasks))
        .order_by(EnterpriseRequest.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        AdminRequestOut(
            id=r.id,
            user_id=r.user_id,
            requester_email=r.user.email,
            text=r.text,
            status=r.status,
            subtask_count=len(r.subtasks),
            created_at=r.created_at,
            completed_at=r.completed_at,
        )
        for r in rows
    ]


@router.get("/users", response_model=list[UserAdminOut])
def list_users(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[User]:
    require_admin(current_user)
    return db.query(User).order_by(User.created_at).all()


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    require_admin(current_user)

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == current_user.id and (
        (payload.role is not None and payload.role != "admin")
        or (payload.is_active is not None and not payload.is_active)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot demote or deactivate your own account.",
        )

    if payload.role is not None:
        if payload.role not in VALID_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role. Valid roles: {', '.join(sorted(VALID_ROLES))}",
            )
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active

    log_event(
        db,
        event_type="admin",
        action="admin.user_update",
        user_id=current_user.id,
        role=current_user.role,
        context={
            "target_user_id": user.id,
            "target_email": user.email,
            "new_role": payload.role,
            "new_is_active": payload.is_active,
        },
    )
    db.commit()
    db.refresh(user)
    return user


@router.get("/permissions", response_model=PermissionsMatrixOut)
def get_permissions(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> PermissionsMatrixOut:
    require_admin(current_user)
    return _build_matrix(db)


@router.post("/permissions/toggle", response_model=PermissionsMatrixOut)
def toggle_permission(
    payload: PermissionToggleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PermissionsMatrixOut:
    require_admin(current_user)

    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role.")
    if payload.agent_type not in get_agent_types():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid agent type.")

    existing = (
        db.query(RolePermission)
        .filter(RolePermission.role == payload.role, RolePermission.agent_type == payload.agent_type)
        .first()
    )
    if payload.allowed and existing is None:
        db.add(RolePermission(role=payload.role, agent_type=payload.agent_type))
        log_event(
            db,
            event_type="admin",
            action="admin.permission_grant",
            user_id=current_user.id,
            role=current_user.role,
            context={"role": payload.role, "agent_type": payload.agent_type},
        )
        db.commit()
    elif not payload.allowed and existing is not None:
        db.delete(existing)
        log_event(
            db,
            event_type="admin",
            action="admin.permission_revoke",
            user_id=current_user.id,
            role=current_user.role,
            context={"role": payload.role, "agent_type": payload.agent_type},
        )
        db.commit()

    return _build_matrix(db)


@router.get("/audit-logs", response_model=list[AuditLogOut])
def list_audit_logs(
    event_type: str | None = None,
    user_id: int | None = None,
    limit: int = Query(default=DEFAULT_AUDIT_LOG_LIMIT, le=MAX_AUDIT_LOG_LIMIT, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AuditLog]:
    require_admin(current_user)
    query = db.query(AuditLog)
    if event_type:
        query = query.filter(AuditLog.event_type == event_type)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    return query.order_by(AuditLog.created_at.desc()).limit(limit).all()


@router.get("/metrics", response_model=EvaluationReport)
def get_metrics(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> EvaluationReport:
    require_admin(current_user)
    return EvaluationReport(**compute_metrics(db))


@router.post("/rag-evaluation/run", response_model=RagEvaluationRunOut)
def run_rag_evaluation(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> RagEvaluationRun:
    # NFR-2: admin-triggered on demand, not automatic -- this makes ~12 real
    # LLM calls and realistically takes a couple of minutes.
    require_admin(current_user)
    report = run_evaluation()
    run = RagEvaluationRun(
        baseline_accuracy=report.baseline_accuracy,
        grounded_accuracy=report.grounded_accuracy,
        cases=[asdict(c) for c in report.cases],
    )
    db.add(run)
    log_event(
        db,
        event_type="admin",
        action="admin.rag_evaluation_run",
        user_id=current_user.id,
        role=current_user.role,
        context={
            "baseline_accuracy": report.baseline_accuracy,
            "grounded_accuracy": report.grounded_accuracy,
        },
    )
    db.commit()
    db.refresh(run)
    return run


@router.get("/rag-evaluation", response_model=RagEvaluationRunOut | None)
def get_latest_rag_evaluation(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> RagEvaluationRun | None:
    require_admin(current_user)
    return db.query(RagEvaluationRun).order_by(RagEvaluationRun.created_at.desc()).first()


@router.get("/trace/{subtask_id}", response_model=DecisionTraceOut)
def get_decision_trace(
    subtask_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DecisionTraceOut:
    """NFR-3: assemble the full causal trail for one decision -- the subtask's
    own detail, its parent request's context, and every audit log entry tied
    to it, in order -- rather than requiring manual cross-referencing across
    three separate views."""
    require_admin(current_user)

    subtask = db.query(SubTask).filter(SubTask.id == subtask_id).first()
    if subtask is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subtask not found")

    audit_trail = (
        db.query(AuditLog)
        .filter(AuditLog.subtask_id == subtask_id)
        .order_by(AuditLog.created_at)
        .all()
    )

    return DecisionTraceOut(
        subtask=subtask,
        request=TraceRequestContext(
            id=subtask.request.id,
            text=subtask.request.text,
            requester_email=subtask.request.user.email,
            status=subtask.request.status,
            created_at=subtask.request.created_at,
            completed_at=subtask.request.completed_at,
        ),
        audit_trail=audit_trail,
    )


@router.get("/system-health")
def get_system_health(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    require_admin(current_user)

    user_count = db.query(User).count()
    active_user_count = db.query(User).filter(User.is_active.is_(True)).count()
    permission_count = db.query(RolePermission).count()

    agents = [
        {"type": agent_type, "sensitive": agent_type in SENSITIVE_AGENT_TYPES}
        for agent_type in sorted(AGENT_REGISTRY.keys())
    ]

    try:
        from app.rag.vector_store import get_collection
        collection = get_collection()
        doc_count = collection.count()
        rag_status = "ok"
    except Exception as exc:
        doc_count = 0
        rag_status = str(exc)

    from app.rag.llm import ollama_available
    ollama_status = "ok" if ollama_available() else "unavailable"

    pending_approvals = db.query(EnterpriseRequest).filter(
        EnterpriseRequest.status == "pending_approval"
    ).count()

    from app.models.sub_task import SubTask
    processing_requests = db.query(EnterpriseRequest).filter(
        EnterpriseRequest.status == "processing"
    ).count()

    return {
        "db": {
            "status": "ok",
            "user_count": user_count,
            "active_user_count": active_user_count,
            "permission_count": permission_count,
        },
        "agents": agents,
        "rag": {"status": rag_status, "document_count": doc_count},
        "llm": {"status": ollama_status},
        "queue": {
            "processing": processing_requests,
            "pending_approvals": pending_approvals,
        },
        "hitl_confidence_threshold": get_hitl_threshold(),
    }


class SettingsUpdate(BaseModel):
    hitl_confidence_threshold: float | None = None


@router.get("/settings")
def get_settings(
    current_user: User = Depends(get_current_user),
) -> dict:
    require_admin(current_user)
    return get_all_settings()


@router.patch("/settings")
def update_settings(
    payload: SettingsUpdate,
    current_user: User = Depends(get_current_user),
) -> dict:
    require_admin(current_user)
    if payload.hitl_confidence_threshold is not None:
        try:
            set_hitl_threshold(payload.hitl_confidence_threshold)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return get_all_settings()


@router.get("/traces", response_model=list[TraceSpanOut])
def list_trace_spans(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TraceSpan]:
    """Observability: flat list of all trace spans for a request, ordered by start time."""
    require_admin(current_user)
    return (
        db.query(TraceSpan)
        .filter(TraceSpan.request_id == request_id)
        .order_by(TraceSpan.started_at)
        .all()
    )


@router.get("/analytics")
def get_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Aggregated analytics for the dashboard."""
    require_admin(current_user)

    from collections import Counter, defaultdict
    from datetime import date, timedelta
    from app.models.sub_task import SubTask
    from app.workflow.functions import MOCK_HEADCOUNT, MOCK_EXPENSE_TOTALS_USD

    # ── Request volume — last 30 days ────────────────────────────────────────
    today = date.today()
    thirty_days_ago = today - timedelta(days=29)
    all_requests = db.query(EnterpriseRequest).filter(
        EnterpriseRequest.created_at >= thirty_days_ago
    ).all()

    daily: dict[str, int] = {}
    for i in range(30):
        daily[(today - timedelta(days=29 - i)).isoformat()] = 0
    for r in all_requests:
        key = r.created_at.date().isoformat()
        if key in daily:
            daily[key] += 1
    requests_by_day = [{"date": k, "count": v} for k, v in daily.items()]

    # ── Request status breakdown ─────────────────────────────────────────────
    status_counts = Counter(
        r.status for r in db.query(EnterpriseRequest).all()
    )

    # ── Subtask stats by agent ────────────────────────────────────────────────
    all_subtasks = db.query(SubTask).all()
    agent_counts: Counter = Counter()
    agent_durations: dict[str, list[int]] = defaultdict(list)
    agent_confidence: dict[str, list[float]] = defaultdict(list)
    hitl_count = 0
    denial_count = 0
    confidence_bins = [0] * 5  # 0-20, 20-40, 40-60, 60-80, 80-100

    for st in all_subtasks:
        agent_counts[st.agent_type] += 1
        if st.duration_ms is not None:
            agent_durations[st.agent_type].append(st.duration_ms)
        if st.confidence is not None:
            agent_confidence[st.agent_type].append(st.confidence)
            bucket = min(int(st.confidence * 5), 4)
            confidence_bins[bucket] += 1
        if st.status == "pending_approval":
            hitl_count += 1
        if st.status in ("denied", "rejected"):
            denial_count += 1

    subtasks_by_agent = [{"agent": k, "count": v} for k, v in sorted(agent_counts.items())]
    avg_duration_by_agent = [
        {"agent": k, "avg_ms": round(sum(v) / len(v))}
        for k, v in agent_durations.items() if v
    ]
    avg_confidence_by_agent = [
        {"agent": k, "avg_pct": round(sum(v) / len(v) * 100)}
        for k, v in agent_confidence.items() if v
    ]

    # ── Top requesters ────────────────────────────────────────────────────────
    user_counts: Counter = Counter(r.user_id for r in db.query(EnterpriseRequest).all())
    user_map = {u.id: u.email for u in db.query(User).all()}
    top_requesters = [
        {"email": user_map.get(uid, "unknown"), "count": cnt}
        for uid, cnt in user_counts.most_common(5)
    ]

    return {
        "requests_by_day": requests_by_day,
        "requests_by_status": dict(status_counts),
        "subtasks_by_agent": subtasks_by_agent,
        "avg_duration_by_agent": avg_duration_by_agent,
        "avg_confidence_by_agent": avg_confidence_by_agent,
        "confidence_bins": [
            {"range": f"{i*20}–{i*20+20}%", "count": confidence_bins[i]}
            for i in range(5)
        ],
        "hitl_escalations": hitl_count,
        "denial_count": denial_count,
        "total_requests": db.query(EnterpriseRequest).count(),
        "total_subtasks": len(all_subtasks),
        "top_requesters": top_requesters,
        "enterprise": {
            "headcount": [{"dept": k, "count": v} for k, v in MOCK_HEADCOUNT.items()],
            "expenses": [{"dept": k, "usd": v} for k, v in MOCK_EXPENSE_TOTALS_USD.items()],
        },
    }


@router.get("/traces/{request_id}/tree")
def get_trace_tree(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Observability: nested span tree for a request, used by the Agent Graph UI."""
    require_admin(current_user)

    req = db.query(EnterpriseRequest).filter(EnterpriseRequest.id == request_id).first()
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    spans = (
        db.query(TraceSpan)
        .filter(TraceSpan.request_id == request_id)
        .order_by(TraceSpan.started_at)
        .all()
    )

    # Build id → dict map, then nest children under parents.
    span_map: dict[int, dict] = {}
    for s in spans:
        span_map[s.id] = {
            "id": s.id,
            "subtask_id": s.subtask_id,
            "parent_span_id": s.parent_span_id,
            "span_type": s.span_type,
            "name": s.name,
            "status": s.status,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "duration_ms": s.duration_ms,
            "input_tokens": s.input_tokens,
            "output_tokens": s.output_tokens,
            "metadata": s.metadata_,
            "children": [],
        }

    roots: list[dict] = []
    for span_dict in span_map.values():
        pid = span_dict["parent_span_id"]
        if pid is not None and pid in span_map:
            span_map[pid]["children"].append(span_dict)
        else:
            roots.append(span_dict)

    total_ms = None
    if req.created_at and req.completed_at:
        delta = req.completed_at - req.created_at
        total_ms = round(delta.total_seconds() * 1000)

    return {
        "request_id": request_id,
        "request_text": req.text,
        "request_status": req.status,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
        "total_duration_ms": total_ms,
        "spans": roots,
    }
