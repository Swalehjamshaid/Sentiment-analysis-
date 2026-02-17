from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, UploadFile, File, Form
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    from datetime import datetime, timedelta
    import secrets, os

    from ..db import engine
    from ..models import User, VerificationToken, ResetToken, LoginAttempt
    from ..schemas import RegisterIn, LoginIn
    from ..utils.security import hash_password, verify_password, issue_jwt, validate_password_strength, ensure_valid_email

    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    router = APIRouter(prefix="/auth", tags=["auth"])

    LOCK_THRESHOLD = 5
    LOCK_MINUTES = 15

    @router.post("/register")
    async def register(full_name: str = Form(..., max_length=100), email: str = Form(...), password: str = Form(...), profile: UploadFile | None = File(None)):
        ensure_valid_email(email)
        if not validate_password_strength(password):
            raise HTTPException(status_code=400, detail="Weak password")
        pic_url = None
        if profile:
            if profile.content_type not in ("image/jpeg", "image/png"):
                raise HTTPException(status_code=400, detail="Profile must be JPEG/PNG")
            content = await profile.read()
            if len(content) > 2*1024*1024:
                raise HTTPException(status_code=400, detail="Profile too large")
            fname = f"profile_{secrets.token_hex(8)}.{ 'jpg' if profile.content_type=='image/jpeg' else 'png'}"
            os.makedirs("app_uploads", exist_ok=True)
            with open(os.path.join("app_uploads", fname), "wb") as f:
                f.write(content)
            pic_url = f"/uploads/{fname}"
        with SessionLocal() as s:
            exists = s.query(User).filter(User.email==email).first()
            if exists:
                raise HTTPException(status_code=400, detail="Email already registered")
            u = User(full_name=full_name, email=email, password_hash=hash_password(password), profile_pic_url=pic_url)
            s.add(u); s.flush()
            vt = VerificationToken(user_id=u.id, token=secrets.token_urlsafe(24), expires_at=datetime.utcnow()+timedelta(hours=24))
            s.add(vt); s.commit()
            # TODO: send verification email with token (stub/logging only)
            return {"message": "Registered. Check email for verification link.", "verify_token": vt.token}

    @router.get("/verify")
    def verify(token: str):
        with SessionLocal() as s:
            vt = s.query(VerificationToken).filter(VerificationToken.token==token, VerificationToken.used==False).first()
            if not vt or vt.expires_at < datetime.utcnow():
                raise HTTPException(status_code=400, detail="Invalid or expired token")
            user = s.query(User).get(vt.user_id)
            user.status = "active"
            vt.used = True
            s.commit()
            return {"message": "Email verified"}

    @router.post("/login")
    async def login(request: Request, payload: LoginIn):
        ip = request.client.host if request.client else "unknown"
        with SessionLocal() as s:
            user = s.query(User).filter(User.email==payload.email).first()
            if not user:
                s.add(LoginAttempt(user_id=None, ip=ip, success=False))
                s.commit()
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
            # lockout check
            if user.locked_until and user.locked_until > datetime.utcnow():
                raise HTTPException(status_code=423, detail="Account locked. Try later or use reset.")
            ok = verify_password(payload.password, user.password_hash)
            s.add(LoginAttempt(user_id=user.id, ip=ip, success=ok))
            if not ok:
                user.failed_attempts = (user.failed_attempts or 0) + 1
                if user.failed_attempts >= LOCK_THRESHOLD:
                    user.locked_until = datetime.utcnow()+timedelta(minutes=LOCK_MINUTES)
                s.commit()
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
            # success
            user.failed_attempts = 0
            user.locked_until = None
            user.last_login = datetime.utcnow()
            token = issue_jwt(str(user.id))
            s.commit()
            resp = {"access_token": token, "token_type": "bearer"}
            return resp

    @router.post("/request-reset")
    def request_reset(email: str):
        with SessionLocal() as s:
            user = s.query(User).filter(User.email==email).first()
            if not user:
                return {"message": "If account exists, a reset link will be sent."}
            rt = ResetToken(user_id=user.id, token=secrets.token_urlsafe(24), expires_at=datetime.utcnow()+timedelta(minutes=30))
            s.add(rt); s.commit()
            return {"message": "Reset link sent.", "reset_token": rt.token}

    @router.post("/reset")
    def reset(token: str, new_password: str, confirm_password: str):
        if new_password != confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")
        if not validate_password_strength(new_password):
            raise HTTPException(status_code=400, detail="Weak password")
        with SessionLocal() as s:
            rt = s.query(ResetToken).filter(ResetToken.token==token, ResetToken.used==False).first()
            if not rt or rt.expires_at < datetime.utcnow():
                raise HTTPException(status_code=400, detail="Invalid or expired token")
            user = s.query(User).get(rt.user_id)
            user.password_hash = hash_password(new_password)
            rt.used = True
            s.commit()
            return {"message": "Password updated"}