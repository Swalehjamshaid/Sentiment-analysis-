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
