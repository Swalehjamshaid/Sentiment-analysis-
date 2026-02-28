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
# This fixes the "module 'bcrypt' has no attribute '__about__'" error
try:
    import bcrypt
    if not hasattr(bcrypt, "__about__"):
        bcrypt.__about__ = type('About', (object,), {'__version__': bcrypt.__version__})
except ImportError:
    pass
# -----------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hashes a plain-text password using bcrypt."""
    return pwd_context.hash(password[:72])

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain-text password against a hash."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

def verify_password_strength(password: str) -> bool:
    """Checks for: 8+ chars, 1 uppercase, 1 lowercase, 1 number."""
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
    """Creates a JWT access token for the session."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_MIN)
    to_encode = {"exp": expire, "sub": str(user_id)}
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    return encoded_jwt

async def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """
    REQUIRED: Fetches the user based on the JWT stored in the cookie.
    This fixes the ImportError causing your 500 error.
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
