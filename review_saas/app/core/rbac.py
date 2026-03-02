
# filename: app/core/rbac.py
from __future__ import annotations
from fastapi import HTTPException

ROLE_POWER = {"viewer": 1, "editor": 5, "admin": 9}

def require_role(user_role: str, needed: str):
    if ROLE_POWER.get(user_role, 0) < ROLE_POWER.get(needed, 0):
        raise HTTPException(status_code=403, detail="Insufficient role")
