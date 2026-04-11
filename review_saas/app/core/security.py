from datetime import datetime, timedelta, timezone
from typing import Optional
import os
import bcrypt
from jose import jwt, JWTError

# Configuration from Railway
SECRET_KEY = os.getenv("SECRET_KEY", "7bd8e1c4a92b3c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t")
ALGORITHM = "HS256"


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt(rounds=12)          # 12 is a good default cost
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def create_verification_token(email: str) -> str:
    """Create a short-lived email verification JWT"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    to_encode = {
        "exp": expire,
        "sub": str(email),
        "type": "email_verification"
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_verification_token(token: str) -> Optional[str]:
    """Decode and validate email verification token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "email_verification":
            return None
        return payload.get("sub")
    except JWTError:
        return None
