# filename: app/security/utils.py
import re
from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext
from ..core.config import settings

pwd_context = CryptContext(schemes=["bcrypt", "argon2"], deprecated="auto")

PASSWORD_REGEX = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$")

def verify_password_strength(pw: str) -> bool:
    return bool(PASSWORD_REGEX.match(pw))

def hash_password(pw: str) -> str:
    return pwd_context.hash(pw)

def verify_password(pw: str, hashed: str) -> bool:
    return pwd_context.verify(pw, hashed)

def create_access_token(subject: str, minutes: int | None = None):
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=minutes or settings.ACCESS_TOKEN_MIN)
    to_encode = {"sub": subject, "iat": int(now.timestamp()), "exp": int(expire.timestamp())}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
