import os, re
    from datetime import datetime, timedelta
    from jose import jwt
    from passlib.context import CryptContext
    from email_validator import validate_email, EmailNotValidError

    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    ALGO = "HS256"

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(p: str) -> str:
        return pwd_context.hash(p)

    def verify_password(p: str, hashed: str) -> bool:
        return pwd_context.verify(p, hashed)

    def issue_jwt(sub: str, minutes: int = 60) -> str:
        exp = datetime.utcnow() + timedelta(minutes=minutes)
        return jwt.encode({"sub": sub, "exp": exp}, SECRET_KEY, algorithm=ALGO)

    def validate_password_strength(p: str) -> bool:
        if len(p) < 8: return False
        if not re.search(r"[A-Z]", p): return False
        if not re.search(r"[a-z]", p): return False
        if not re.search(r"[0-9]", p): return False
        if not re.search(r"[^A-Za-z0-9]", p): return False
        return True

    def ensure_valid_email(e: str) -> None:
        try:
            validate_email(e)
        except EmailNotValidError as ex:
            raise ValueError(str(ex))

    def sanitize_text(t: str | None) -> str:
        t = (t or "").strip()
        # simplistic sanitization
        t = t.replace("<", "&lt;").replace(">", "&gt;")
        return t