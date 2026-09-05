from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.role_permission import RolePermission
from app.models.user import User

VALID_ROLES = {"employee", "hr", "admin"}

# What a fresh system starts with -- used only by app.rbac.seed's one-time
# seed. Live permission checks (can_use_agent) read from the DB
# (role_permissions), which is admin-editable per FR-11.
DEFAULT_ROLE_AGENT_PERMISSIONS: dict[str, set[str]] = {
    "employee": {"rag", "workflow", "validation", "analytics"},
    "hr": {"rag", "workflow", "validation", "security", "analytics"},
    "admin": {"rag", "workflow", "validation", "security", "analytics"},
}


def get_agent_types() -> set[str]:
    """NFR-4: derived from the agent registry rather than a separately
    maintained literal set -- one source of truth, so registering a new
    agent type is immediately manageable through the FR-11 admin
    Permissions UI too.

    Imported lazily (not at module load): app.agents.registry transitively
    imports this module (registry -> rag_agent -> app.rag.pipeline -> here,
    for VALID_ROLES), so a top-level import of the registry would be circular.
    """
    from app.agents.registry import AGENT_REGISTRY

    return set(AGENT_REGISTRY.keys())


def can_use_agent(role: str, agent_type: str, db: Session) -> bool:
    return (
        db.query(RolePermission)
        .filter(RolePermission.role == role, RolePermission.agent_type == agent_type)
        .first()
        is not None
    )


# NFR-9 (Maintainability): a single, shared admin-gate check -- previously
# duplicated near-identically as a local _require_admin() in both
# app/api/routes/admin.py and app/api/routes/approvals.py.
def require_admin(user: User, detail: str = "Only admins may access this.") -> None:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
