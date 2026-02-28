from passlib.context import CryptContext
import logging
import re

# Set up logging to track any hashing issues
logger = logging.getLogger("review_saas")

# We explicitly set the schemes and force the 'bcrypt' backend 
# to avoid the 'PasswordSizeError' bug in Python 3.13
pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto",
    # This is the key setting to bypass the Python 3.13 compatibility bug
    bcrypt__truncate_error=False  
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
            
        # Explicitly truncate to 72 characters 
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
            
        # Use the same truncation logic for verification
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
