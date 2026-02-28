from datetime import datetime, timedelta
    from jose import jwt
    from passlib.context import CryptContext
    from ..core.settings import settings

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(password: str, hashed: str) -> bool:
        return pwd_context.verify(password, hashed)

    def issue_token(sub: str, minutes: int | None = None) -> str:
        exp = datetime.utcnow() + timedelta(minutes=minutes or settings.JWT_EXP_MINUTES)
        payload = {"sub": sub, "exp": exp}
        return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")