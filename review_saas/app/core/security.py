# filename: app/core/security.py
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request, HTTPException, status, Depends
from jose import jwt, JWTError
from passlib.context import CryptContext
import passlib.handlers.bcrypt
from sqlalchemy.orm import Session

from .settings import settings
from .db import get_db
from ..models.models import User

# --- FIX: Passlib + Bcrypt 4.x compatibility monkeypatch ---
try:
    import bcrypt
    if not hasattr(bcrypt, "__about__"):
        bcrypt.__about__ = type('About', (object,), {'__version__': bcrypt.__version__})
except ImportError:
    pass
# -----------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hashes a plain-text password."""
    return pwd_context.hash(password[:72])

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain-text password against a hash."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

def verify_password_strength(password: str) -> bool:
    """Requirement #6: Password Complexity."""
    if len(password) < 8:
        return False
    if not any(char.isdigit() for char in password):
        return False
    if not any(char.isupper() for char in password):
        return False
    if not any(char.islower() for char in password):
        return False
    return True

# --- JWT & Authentication Logic ---

def create_access_token(user_id: str) -> str:
    """Requirement #8: Create JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_MIN)
    to_encode = {"exp": expire, "sub": str(user_id)}
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    return encoded_jwt

async def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """
    Requirement #9: Dependency to get the currently logged-in user 
    via the HTTP-only cookie.
    """
    token = request.cookies.get("access_token")
    if not token:
        return None
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    return user

def login_required(user: Optional[User] = Depends(get_current_user)):
    """Simple helper to enforce login on specific routes."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"}
        )
    return user
