from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form, Request
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    from datetime import datetime, timedelta
    import secrets, os

    from ..db import engine
    from ..models import User, VerificationToken, ResetToken, LoginAttempt
    from ..utils.security import hash_password, verify_password, issue_jwt, validate_password_strength, ensure_valid_email
    from ..utils.emailer import send_email
    from ..utils.totp import new_secret, verify_totp
    from ..utils.oauth import oauth
    from ..core.config import settings

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    router = APIRouter(prefix="/auth", tags=["auth"])

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
            os.makedirs("app_uploads", exist_ok=True)
            ext = 'jpg' if profile.content_type=='image/jpeg' else 'png'
            fname = f"profile_{secrets.token_hex(8)}.{ext}"
            with open(os.path.join("app_uploads", fname), "wb") as f: f.write(content)
            pic_url = f"/uploads/{fname}"
        with SessionLocal() as s:
            if s.query(User).filter(User.email==email).first():
                raise HTTPException(status_code=400, detail="Email already registered")
            u = User(full_name=full_name, email=email, password_hash=hash_password(password), profile_pic_url=pic_url)
            s.add(u); s.flush()
            vt = VerificationToken(user_id=u.id, token=secrets.token_urlsafe(24), expires_at=datetime.utcnow()+timedelta(hours=24))
            s.add(vt); s.commit()
            link = f"/auth/verify?token={vt.token}"
            send_email(u.email, "Verify your account", f"Click to verify: {link}")
            return {"message": "Registered. Check email for verification link.", "verify_token": vt.token}

    @router.get("/verify")
    def verify(token: str):
        with SessionLocal() as s:
            vt = s.query(VerificationToken).filter(VerificationToken.token==token, VerificationToken.used==False).first()
            if not vt or vt.expires_at < datetime.utcnow():
                raise HTTPException(status_code=400, detail="Invalid or expired token")
            user = s.get(User, vt.user_id)
            user.status = "active"; vt.used = True; s.commit()
            return {"message": "Email verified"}

    @router.post("/login")
    def login(request: Request, email: str, password: str, totp: str | None = None):
        ip = request.client.host if request.client else "unknown"
        with SessionLocal() as s:
            user = s.query(User).filter(User.email==email).first()
            if not user:
                s.add(LoginAttempt(user_id=None, ip=ip, success=False)); s.commit()
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
            if user.locked_until and user.locked_until > datetime.utcnow():
                raise HTTPException(status_code=423, detail="Account locked. Try later or reset password.")
            ok = verify_password(password, user.password_hash)
            s.add(LoginAttempt(user_id=user.id, ip=ip, success=ok))
            if not ok:
                user.failed_attempts = (user.failed_attempts or 0) + 1
                if user.failed_attempts >= 5:
                    from datetime import timedelta
                    user.locked_until = datetime.utcnow()+timedelta(minutes=15)
                s.commit();
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
            if settings.ENABLE_2FA and user.twofa_secret:
                if not (totp and verify_totp(user.twofa_secret, totp)):
                    raise HTTPException(status_code=401, detail="2FA required or invalid code")
            user.failed_attempts = 0; user.locked_until = None; user.last_login = datetime.utcnow(); s.commit()
            token = issue_jwt(str(user.id))
            return {"access_token": token, "token_type": "bearer"}

    @router.post("/enable-2fa")
    def enable_2fa(user_email: str):
        with SessionLocal() as s:
            u = s.query(User).filter(User.email==user_email).first()
            if not u:
                raise HTTPException(404, "User not found")
            from ..utils.totp import new_secret
            u.twofa_secret = new_secret(); s.commit()
            return {"secret": u.twofa_secret}

    @router.post("/request-reset")
    def request_reset(email: str):
        with SessionLocal() as s:
            user = s.query(User).filter(User.email==email).first()
            if not user: return {"message": "If account exists, a reset link will be sent."}
            rt = ResetToken(user_id=user.id, token=secrets.token_urlsafe(24), expires_at=datetime.utcnow()+timedelta(minutes=30))
            s.add(rt); s.commit()
            send_email(user.email, "Reset password", f"Reset token: {rt.token}")
            return {"message": "Reset link sent.", "reset_token": rt.token}

    @router.post("/reset")
    def reset(token: str, new_password: str, confirm_password: str):
        if new_password != confirm_password:
            raise HTTPException(400, "Passwords do not match")
        if not validate_password_strength(new_password):
            raise HTTPException(400, "Weak password")
        with SessionLocal() as s:
            rt = s.query(ResetToken).filter(ResetToken.token==token, ResetToken.used==False).first()
            if not rt or rt.expires_at < datetime.utcnow():
                raise HTTPException(400, "Invalid or expired token")
            user = s.get(User, rt.user_id); user.password_hash = hash_password(new_password); rt.used = True; s.commit()
            return {"message": "Password updated"}

    # Google OAuth optional
    @router.get('/google/login')
    async def google_login(request: Request):
        if not oauth.client('google'):
            raise HTTPException(400, 'Google OAuth not configured')
        redirect_uri = settings.OAUTH_REDIRECT_URL or str(request.url_for('google_callback'))
        return await oauth.google.authorize_redirect(request, redirect_uri)

    @router.get('/google/callback')
    async def google_callback(request: Request):
        if not oauth.client('google'):
            raise HTTPException(400, 'Google OAuth not configured')
        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get('userinfo')
        email = userinfo and userinfo.get('email')
        if not email:
            raise HTTPException(400, 'Email not available from Google')
        with SessionLocal() as s:
            u = s.query(User).filter(User.email==email).first()
            if not u:
                u = User(full_name=userinfo.get('name') or email.split('@')[0], email=email, password_hash=hash_password(secrets.token_urlsafe(12)), status='active')
                s.add(u); s.commit(); s.refresh(u)
            token = issue_jwt(str(u.id))
            return {"access_token": token, "token_type": "bearer"}