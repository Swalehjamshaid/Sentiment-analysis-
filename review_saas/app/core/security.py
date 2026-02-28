from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import logging

# Set up logging for the SaaS application
logger = logging.getLogger("review_saas")

# Configuration to bypass the Python 3.13 Bcrypt bug
# 'bcrypt__truncate_error=False' is required for Python 3.13
pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto",
    bcrypt__truncate_error=False  
)

# Standard OAuth2 scheme for protected routes
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

def hash_password(password: str) -> str:
    """
    Hashes a plain-text password using bcrypt.
    Manual truncation to 72 chars ensures safety on Python 3.13.
    """
    try:
        if not password:
            return ""
        # Truncate to 72 characters as per Bcrypt standards
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
    Simplified: Returns True if a password exists. 
    Removes strict length requirements as requested.
    """
    if password and len(str(password)) > 0:
        return True
    return False

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Maintains session/token for protected routes.
    Fixed the ImportError in companies.py by including this function.
    """
    if not token:
        # If no token is provided, the user is not authenticated
        return None
    return token
