from datetime import datetime, timedelta, timezone
from typing import Optional
import os
from jose import jwt, JWTError
from passlib.context import CryptContext

# Configuration from Railway
SECRET_KEY = os.getenv("SECRET_KEY", "7bd8e1c4a92b3c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t")
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_verification_token(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    to_encode = {
        "exp": expire, 
        "sub": str(email), 
        "type": "email_verification"
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_verification_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "email_verification":
            return None
        return payload.get("sub")
    except JWTError:
        return None
