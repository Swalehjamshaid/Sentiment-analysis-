# File: app/core/security.py
from __future__ import annotations
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..models.models import User

async def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Pure session-based authentication."""
    try:
        user_id = request.session.get("user_id") if "session" in request.scope else None
    except Exception:
        user_id = None

    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user
