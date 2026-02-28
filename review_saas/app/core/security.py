# File: app/core/security.py

from passlib.context import CryptContext
import logging
import re

logger = logging.getLogger("review_saas")

pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto", 
    bcrypt__truncate_error=False
)

def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty")
    safe_password = str(password)[:72]
    return pwd_context.hash(safe_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False
    return pwd_context.verify(str(plain_password)[:72], hashed_password)

def verify_password_strength(password: str) -> bool:
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"\d", password):
        return
