from collections.abc import Generator
from typing import Optional

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    email = decode_access_token(token)
    if email is None:
        raise credentials_error

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_error

    # Zero-Trust (FR-5): re-checked on every request, not just at login --
    # an already-issued, unexpired token from a deactivated account is
    # rejected immediately rather than trusted until it expires.
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_user_sse(
    request: Request,
    token_query: Optional[str] = Query(default=None, alias="token"),
    db: Session = Depends(get_db),
) -> User:
    """Like get_current_user but also accepts Bearer token via ?token= query param.

    EventSource (SSE) does not support custom headers, so the browser passes
    the JWT as a query parameter instead.
    """
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Prefer Authorization header; fall back to ?token= query param.
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        raw_token = auth_header[len("Bearer "):]
    elif token_query:
        raw_token = token_query
    else:
        raise credentials_error

    email = decode_access_token(raw_token)
    if email is None:
        raise credentials_error

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_error

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
