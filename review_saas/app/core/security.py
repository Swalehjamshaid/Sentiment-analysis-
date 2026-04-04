from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
# Assumes settings exists in your app/core/config.py
from app.core.config import settings 

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """Hashes a plain text password using bcrypt."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Checks a plain text password against the stored hash."""
    return pwd_context.verify(plain_password, hashed_password)

def create_verification_token(email: str) -> str:
    """Generates a 30-minute JWT token for email verification."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    to_encode = {
        "exp": expire, 
        "sub": str(email), 
        "type": "email_verification"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_verification_token(token: str) -> Optional[str]:
    """Decodes the JWT and returns the email if valid, else None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "email_verification":
            return None
        return payload.get("sub")
    except JWTError:
        return None
