# filename: app/core/security.py
from passlib.context import CryptContext
import logging

# --- FIX: Passlib + Bcrypt 4.x compatibility monkeypatch ---
import passlib.handlers.bcrypt
# This prevents the AttributeError: module 'bcrypt' has no attribute '__about__'
if hasattr(passlib.handlers.bcrypt, "_bcrypt"):
    try:
        import bcrypt
        if not hasattr(bcrypt, "__about__"):
            # Manually inject the attribute Passlib is looking for
            bcrypt.__about__ = type('About', (object,), {'__version__': bcrypt.__version__})
    except ImportError:
        pass
# -----------------------------------------------------------

# Requirement #7: Password Hashing using Argon2 or Bcrypt
# Using bcrypt (via passlib)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hashes a plain-text password."""
    # Bcrypt has a 72-character limit, so we truncate to prevent errors
    return pwd_context.hash(password[:72])

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain-text password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)

def verify_password_strength(password: str) -> bool:
    """
    Requirement #6: Password Complexity
    Checks for: 8+ chars, 1 uppercase, 1 lowercase, 1 number.
    """
    if len(password) < 8:
        return False
    if not any(char.isdigit() for char in password):
        return False
    if not any(char.isupper() for char in password):
        return False
    if not any(char.islower() for char in password):
        return False
    return True

# --- JWT Token Logic ---
from datetime import datetime, timedelta, timezone
from jose import jwt
from .settings import settings

def create_access_token(user_id: str) -> str:
    """Requirement #8: Create JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_MIN)
    to_encode = {"exp": expire, "sub": user_id}
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    return encoded_jwt
