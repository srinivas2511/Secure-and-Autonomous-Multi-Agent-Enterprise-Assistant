from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.audit.logger import log_event
from app.models.sub_task import SubTask
from app.models.user import User
from app.orchestrator.orchestrator import compute_request_status
from app.rbac.roles import require_admin
from app.schemas.approval import PendingApprovalOut, RejectRequest

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def _get_pending_subtask(subtask_id: int, db: Session) -> SubTask:
    subtask = db.query(SubTask).filter(SubTask.id == subtask_id).first()
    if subtask is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subtask not found")
    if subtask.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Subtask is not pending approval (status='{subtask.status}').",
        )
    return subtask


def _to_out(subtask: SubTask) -> PendingApprovalOut:
    return PendingApprovalOut(
        id=subtask.id,
        agent_type=subtask.agent_type,
        description=subtask.description,
        status=subtask.status,
        result=subtask.result,
        confidence=subtask.confidence,
        explanation=subtask.explanation,
        created_at=subtask.created_at,
        request_id=subtask.request_id,
        request_text=subtask.request.text,
        requester_email=subtask.request.user.email,
    )


@router.get("/count")
def get_pending_count(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    require_admin(current_user, "Only admins may review pending approvals.")
    count = db.query(SubTask).filter(SubTask.status == "pending_approval").count()
    return {"count": count}


@router.get("", response_model=list[PendingApprovalOut])
def list_pending_approvals(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[PendingApprovalOut]:
    require_admin(current_user, "Only admins may review pending approvals.")
    subtasks = (
        db.query(SubTask)
        .filter(SubTask.status == "pending_approval")
        .order_by(SubTask.created_at)
        .all()
    )
    return [_to_out(s) for s in subtasks]


@router.post("/{subtask_id}/approve", response_model=PendingApprovalOut)
def approve_subtask(
    subtask_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PendingApprovalOut:
    require_admin(current_user, "Only admins may review pending approvals.")
    subtask = _get_pending_subtask(subtask_id, db)

    subtask.status = "completed"
    subtask.approved_by = current_user.id
    subtask.approved_at = datetime.now(timezone.utc)
    subtask.request.status = compute_request_status(subtask.request.subtasks)
    log_event(
        db,
        event_type="approval",
        action="approval.approve",
        user_id=current_user.id,
        role=current_user.role,
        request_id=subtask.request_id,
        subtask_id=subtask.id,
        context={"agent_type": subtask.agent_type},
    )
    db.commit()
    db.refresh(subtask)

    return _to_out(subtask)


@router.post("/{subtask_id}/reject", response_model=PendingApprovalOut)
def reject_subtask(
    subtask_id: int,
    payload: RejectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PendingApprovalOut:
    require_admin(current_user, "Only admins may review pending approvals.")
    subtask = _get_pending_subtask(subtask_id, db)

    subtask.status = "rejected"
    subtask.approved_by = current_user.id
    subtask.approved_at = datetime.now(timezone.utc)
    if payload.reason:
        subtask.explanation = f"{subtask.explanation} [Rejected: {payload.reason}]"
    subtask.request.status = compute_request_status(subtask.request.subtasks)
    log_event(
        db,
        event_type="approval",
        action="approval.reject",
        user_id=current_user.id,
        role=current_user.role,
        request_id=subtask.request_id,
        subtask_id=subtask.id,
        context={"agent_type": subtask.agent_type, "reason": payload.reason},
    )
    db.commit()
    db.refresh(subtask)

    return _to_out(subtask)
