# filename: app/services/security.py
import re
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from passlib.context import CryptContext
from flask import current_app
import jwt
from ..core.config import Settings

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

PASSWORD_REGEX = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).{8,}$")

def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_ctx.verify(password, password_hash)

def validate_password_strength(password: str) -> bool:
    return bool(PASSWORD_REGEX.match(password))

# JWT helpers

def create_jwt(payload: dict) -> str:
    s = Settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.jwt_exp_minutes)
    to_encode = {**payload, 'exp': exp}
    return jwt.encode(to_encode, s.jwt_secret, algorithm='HS256')

def decode_jwt(token: str) -> dict:
    s = Settings()
    return jwt.decode(token, s.jwt_secret, algorithms=['HS256'])

# Tokens (verification / reset)

def new_token() -> str:
    return token_urlsafe(48)
