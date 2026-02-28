from passlib.context import CryptContext
import logging

# Set up logging to track any hashing issues
logger = logging.getLogger("review_saas")

# Configuration to bypass the Python 3.13 Bcrypt bug
# 'bcrypt__truncate_error=False' is critical to stop the PasswordSizeError
pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto",
    bcrypt__truncate_error=False  
)

def hash_password(password: str) -> str:
    """
    Hashes a plain-text password using bcrypt.
    Bcrypt has a natural limit of 72 characters; we truncate to ensure 
    consistency and prevent crashes.
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
        # Check if either input is missing
        if not plain_password or not hashed_password:
            return False
            
        # Use the same truncation logic for verification
        return pwd_context.verify(str(plain_password)[:72], hashed_password)
    except Exception as e:
        logger.error(f"Error verifying password: {str(e)}")
        return False

def verify_password_strength(password: str) -> bool:
    """
    Basic check for password length.
    """
    if not password:
        return False
    # Ensure the password meets a minimum length requirement of 8 characters
    if len(password) < 8:
        return False
    return True
