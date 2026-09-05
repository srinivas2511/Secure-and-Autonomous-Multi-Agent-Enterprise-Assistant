from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.enterprise_request import EnterpriseRequest
from app.models.user import User
from app.orchestrator.orchestrator import run_orchestration
from app.schemas.request import RequestCreate, RequestOut

router = APIRouter(prefix="/api/requests", tags=["requests"])


@router.post("", response_model=RequestOut, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: RequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EnterpriseRequest:
    enterprise_request = EnterpriseRequest(
        user_id=current_user.id, text=payload.text, status="received"
    )
    db.add(enterprise_request)
    db.commit()
    db.refresh(enterprise_request)
    return run_orchestration(enterprise_request, db)


@router.get("", response_model=list[RequestOut])
def list_requests(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[EnterpriseRequest]:
    return (
        db.query(EnterpriseRequest)
        .filter(EnterpriseRequest.user_id == current_user.id)
        .order_by(EnterpriseRequest.created_at.desc())
        .all()
    )


@router.get("/{request_id}", response_model=RequestOut)
def get_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EnterpriseRequest:
    query = db.query(EnterpriseRequest).filter(EnterpriseRequest.id == request_id)
    # Admins can view any request; other roles see only their own.
    if current_user.role != "admin":
        query = query.filter(EnterpriseRequest.user_id == current_user.id)
    enterprise_request = query.first()
    if enterprise_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return enterprise_request
