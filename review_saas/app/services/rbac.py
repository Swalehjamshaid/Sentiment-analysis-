# FILE: app/services/rbac.py

from dataclasses import dataclass
from typing import List, Optional, Callable
from fastapi import Depends, HTTPException, Request

# You can swap this with a DB lookup later
@dataclass
class CurrentUser:
    id: Optional[int]
    email: Optional[str]
    full_name: Optional[str]
    role: str = "owner"

    # For Jinja: behave like Flask-Login's interface
    @property
    def is_authenticated(self) -> bool:
        return bool(self.id)


def get_current_user(request: Request) -> Optional[CurrentUser]:
    """
    Read a simple 'user' dict from session. You can replace with a real auth system.
    """
    u = request.session.get("user")
    if not u:
        return None
    return CurrentUser(
        id=u.get("id"),
        email=u.get("email"),
        full_name=u.get("full_name"),
        role=u.get("role", "owner")
    )


def is_authenticated(request: Request) -> bool:
    return get_current_user(request) is not None


def require_roles(roles: List[str]) -> Callable:
    """
    Dependency guard: ensures current user has one of the allowed roles.
    """
    def _inner(user: Optional[CurrentUser] = Depends(get_current_user)):
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return None
    return _inner
