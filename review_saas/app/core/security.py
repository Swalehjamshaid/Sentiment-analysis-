# File: app/core/security.py

from passlib.context import CryptContext
import logging
import re
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from ..models.models import User
from sqlalchemy.orm import Session

# Set up logging to track any hashing issues
logger = logging.getLogger("review_saas")

# Cryptographic context for password hashing
pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto",
    bcrypt__truncate_error=False  # Avoid Python 3.13 bug
)

def hash_password(password: str) -> str:
    """
    Hashes a plain-text password using bcrypt.
    Bcrypt has a natural limit of 72 characters; we truncate to ensure 
    consistency and prevent 'PasswordSizeError'.
    """
    try:
        if not password:
            raise ValueError("Password cannot be empty")
        safe_password = str(password)[:72]
        return pwd_context.hash(safe_password)
    except Exception as e:
        logger.error(f"Error hashing password: {str(e)}")
        raise e

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain-text password against a stored hashed version.
    """
    try:
        if not plain_password or not hashed_password:
            return False
        return pwd_context.verify(str(plain_password)[:72], hashed_password)
    except Exception as e:
        logger.error(f"Error verifying password: {str(e)}")
        return False

def verify_password_strength(password: str) -> bool:
    """
    Validates the strength of a password.
    Criteria: At least 8 characters, one uppercase, one lowercase, one digit.
    """
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    return True

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
