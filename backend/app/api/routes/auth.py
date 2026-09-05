from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.audit.logger import log_event
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.rbac.roles import VALID_ROLES
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserOut

DEMO_PASSWORD = "demo1234"
DEMO_ACCOUNTS = {
    "admin":    {"email": "admin@demo.local",    "full_name": "Demo Admin"},
    "hr":       {"email": "hr@demo.local",       "full_name": "Demo HR"},
    "employee": {"email": "employee@demo.local", "full_name": "Demo Employee"},
}

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.flush()  # assigns user.id without committing, so the audit entry below lands atomically with it
    log_event(db, event_type="auth", action="auth.register", user_id=user.id, role=user.role)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Token:
    user = db.query(User).filter(User.email == form_data.username).first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        # NFR-1: the HTTP response stays identical either way -- only the
        # (admin-only) audit context distinguishes unknown-email from
        # bad-password, so nothing about account existence leaks to the caller.
        log_event(
            db,
            event_type="auth",
            action="auth.login_failure",
            user_id=user.id if user else None,
            role=user.role if user else None,
            context={
                "email": form_data.username,
                "reason": "unknown_email" if user is None else "bad_password",
            },
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    log_event(db, event_type="auth", action="auth.login_success", user_id=user.id, role=user.role)
    db.commit()
    return Token(access_token=create_access_token(subject=user.email))


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user


class DemoLoginRequest(BaseModel):
    role: str


@router.post("/demo-login", response_model=Token)
def demo_login(payload: DemoLoginRequest, db: Session = Depends(get_db)) -> Token:
    """Seed and instantly sign in as a demo account for a given role.
    Creates the account on first use; idempotent thereafter."""
    if payload.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Valid roles: {', '.join(sorted(VALID_ROLES))}",
        )
    info = DEMO_ACCOUNTS.get(payload.role)
    if info is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No demo account for this role.")

    user = db.query(User).filter(User.email == info["email"]).first()
    if user is None:
        user = User(
            email=info["email"],
            hashed_password=hash_password(DEMO_PASSWORD),
            full_name=info["full_name"],
            role=payload.role,
        )
        db.add(user)
        db.flush()
        log_event(db, event_type="auth", action="auth.demo_seed", user_id=user.id, role=user.role)
        db.commit()
        db.refresh(user)
    elif user.role != payload.role:
        user.role = payload.role
        db.commit()

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo account is deactivated.")

    log_event(db, event_type="auth", action="auth.demo_login", user_id=user.id, role=user.role)
    db.commit()
    return Token(access_token=create_access_token(subject=user.email))
