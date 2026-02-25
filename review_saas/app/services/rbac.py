# FILE: app/services/rbac.py
from typing import Optional, List, Callable
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, UserCompanyRole

def _attach_is_authenticated(user: Optional[User]) -> Optional[User]:
    if user is not None and not hasattr(user, "is_authenticated"):
        # Attach a convenience attribute so Jinja `{% if current_user and current_user.is_authenticated %}`
        setattr(user, "is_authenticated", True)
    return user

def get_current_user(
    request: Request = None,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    1) Works as a dependency in API routes.
    2) Works when called directly from `app.main.common_context`.
    Expects a session key 'user_id' set on login.
    """
    try:
        user_id = None
        if request is not None:
            # Starlette SessionMiddleware places dict at request.session
            user_id = request.session.get("user_id")
        if not user_id:
            return None
        user = db.query(User).filter(User.id == int(user_id)).first()
        return _attach_is_authenticated(user)
    except Exception:
        return None


def require_roles(allowed: List[str]) -> Callable:
    """
    Dependency to enforce RBAC on API endpoints.
    If no roles table yet for the user, you can extend logic to allow owner/admin via user.status.
    """
    def _inner(
        request: Request,
        db: Session = Depends(get_db),
        user: Optional[User] = Depends(get_current_user),
    ):
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        # Collect roles across companies (simple presence check)
        rows = db.query(UserCompanyRole.role).filter(UserCompanyRole.user_id == user.id).all()
        user_roles = {r[0] for r in rows}
        # Fallback to status/admin role if you keep that on user
        if hasattr(user, "role") and getattr(user, "role") == "admin":
            return None
        if not user_roles.intersection(set(allowed)):
            raise HTTPException(status_code=403, detail="Forbidden")
        return None
    return _inner
