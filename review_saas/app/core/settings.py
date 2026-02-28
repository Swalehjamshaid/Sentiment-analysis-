# File: review_saas/app/core/security.py
from __future__ import annotations
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..models.models import User

async def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    PURE SESSION-BASED AUTH — NO TOKEN REQUIRED.
    Reads only request.session['user_id'].
    """
    try:
        if "session" in request.scope:
            user_id = request.session.get("user_id")
        else:
            user_id = None
    except Exception:
        user_id = None

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user
