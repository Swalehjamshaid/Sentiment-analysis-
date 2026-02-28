# filename: review_saas/app/core/security.py
from __future__ import annotations
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .settings import settings
from .db import get_db
from ..models.models import User

# Configure logger for security events
logger = logging.getLogger('app.security')

# Requirement #7: Industry-standard password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Requirement #3: Strong password policy (8+ chars, Upper, Lower, Digit, Special)
PASSWORD_REGEX = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).{8,}$")

def verify_password_strength(password: str) -> bool:
    """Requirement #3: Validates password against security policy."""
    return bool(PASSWORD_REGEX.match(password))

def hash_password(password: str) -> str:
    """Requirement #7 & #29: Hashes password with 72-byte safety for Bcrypt."""
    return pwd_context.hash(password[:72])

def verify_password(password: str, hashed: str) -> bool:
    """Verifies a plain text password against the stored hash."""
    return pwd_context.verify(password, hashed)

def create_access_token(sub: str, minutes: int | None = None) -> str:
    """Requirement #8: Generates a JWT for session management."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=minutes or settings.ACCESS_TOKEN_MIN
    )
    to_encode = {"sub": str(sub), "exp": expire}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALG)

async def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Requirement #42: Identifies the logged-in owner via HTTP-only cookie."""
    # Retrieve token from cookies (Requirement #8)
    token = request.cookies.get("access_token")
    if not token:
        logger.warning("Unauthorized access attempt: No token found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Not logged in"
        )
    
    try:
        # Decode and validate JWT
        payload = jwt.decode(
            token, 
            settings.JWT_SECRET, 
            algorithms=[settings.JWT_ALG]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid session"
            )
    except JWTError:
        logger.warning("Unauthorized access attempt: Token expired or invalid")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Session expired"
        )

    # Fetch user from database to ensure they still exist
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="User not found"
        )
    
    return user
