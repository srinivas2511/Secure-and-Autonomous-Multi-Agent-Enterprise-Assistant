from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AdminRequestOut]:
    """Admin view: all requests across all users, newest first."""
    require_admin(current_user)
    rows = (
        db.query(EnterpriseRequest)
        .order_by(EnterpriseRequest.created_at.desc())
        .limit(200)
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
        {
            "type": agent_type,
            "sensitive": agent_type in SENSITIVE_AGENT_TYPES,
        }
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

    return {
        "db": {
            "status": "ok",
            "user_count": user_count,
            "active_user_count": active_user_count,
            "permission_count": permission_count,
        },
        "agents": agents,
        "rag": {"status": rag_status, "document_count": doc_count},
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
