# filename: app/core/security.py
from __future__ import annotations
import re  # Moved import to the top for better practice
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt
from passlib.context import CryptContext
from fastapi import HTTPException
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# FIXED: Using triple quotes to allow single and double quotes inside the regex
_policy = re.compile(r"""^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[~!@#$%^&*()_+\-={}\[\]:;"'<>,.?/]).{8,}$""")

def validate_password_strength(pw: str) -> bool:
    return bool(_policy.match(pw))

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

# JWT helpers

def create_access_token(sub: str, expires_minutes: int | None = None, extra: dict | None = None) -> str:
    to_encode = {"sub": sub, **(extra or {})}
    # Ensure we use the setting name from your config (ACCESS_TOKEN_MIN or ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(tz=timezone.utc) + timedelta(
        minutes=expires_minutes or int(settings.ACCESS_TOKEN_MIN)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALG)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
