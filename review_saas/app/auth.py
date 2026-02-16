# review_saas/app/auth.py
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, Form
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from email_validator import validate_email, EmailNotValidError
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from jose import jwt
import os, re, bleach, pyotp

from .db import get_db
from .models import User, LoginAttempt
from .schemas import UserLogin
from .utils.security import verify_password, get_password_hash, create_access_token, ALGORITHM
from .config import (
    SECRET_KEY,
    TOKEN_EXPIRE_EMAIL_VERIFICATION_H,
    TOKEN_EXPIRE_PASSWORD_RESET_MIN,
    LOCKOUT_MAX_ATTEMPTS,
    LOCKOUT_DURATION_MIN,
    GOOGLE_OAUTH,
)
from .services.emailer import send_email
from .deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])
serializer = URLSafeTimedSerializer(SECRET_KEY)

def _client_ip(req: Request) -> str:
    return req.client.host if req.client else "unknown"

# ---------------- Registration ----------------
@router.post("/register")
async def register(
    req: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    profile_picture: UploadFile | None = File(None),
    db: Session = Depends(get_db)
):
    # Validate & normalize email
    try:
        v = validate_email(email)
        email_norm = v.email
    except EmailNotValidError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check duplicate
    if db.query(User).filter(User.email == email_norm).first():
        raise HTTPException(status_code=400, detail="Email already registered")  # (28)

    # Password strength (3, 29)
    if len(password) < 8 or not re.search(r"[A-Z]", password) or not re.search(r"[a-z]", password) or not re.search(r"\d", password) or not re.search(r"[^A-Za-z0-9]", password):
        raise HTTPException(status_code=400, detail="Weak password")

    # Optional profile picture (4)
    pic_url = None
    if profile_picture:
        if profile_picture.content_type not in ("image/jpeg", "image/png"):
            raise HTTPException(status_code=400, detail="Only JPEG/PNG allowed")
        content = await profile_picture.read()
        if len(content) > 2 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Max 2MB allowed")
        os.makedirs("uploads/profile_pics", exist_ok=True)
        safe_name = f"{int(datetime.utcnow().timestamp())}_{os.path.basename(profile_picture.filename)}"
        path = os.path.join("uploads", "profile_pics", safe_name)
        with open(path, "wb") as f:
            f.write(content)
        pic_url = f"/uploads/profile_pics/{safe_name}"

    # Sanitize full name (17)
    full_name = bleach.clean(full_name[:100], strip=True)

    # Create user & email verification (5–6)
    token = serializer.dumps({"email": email_norm}, salt="email-verify")
    user = User(
        full_name=full_name,
        email=email_norm,
        password_hash=get_password_hash(password),
        profile_pic_url=pic_url,
        email_verification_token=token,
        email_verification_expires=datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_EMAIL_VERIFICATION_H),
    )
    db.add(user); db.commit(); db.refresh(user)

    verify_link = f"/auth/verify?token={token}"
    # You may want to pass absolute URL; for Railway, you can prepend your public domain.
    send_email(email_norm, "Verify your email", f"<p>Click to verify: <a href='{verify_link}'>Verify</a></p>")
    return {"message": "Registered. Please verify your email."}

@router.get("/verify")
async def verify_email(token: str, db: Session = Depends(get_db)):
    try:
        data = serializer.loads(token, salt="email-verify", max_age=TOKEN_EXPIRE_EMAIL_VERIFICATION_H * 3600)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail="Verification token expired")
    except BadSignature:
        raise HTTPException(status_code=400, detail="Invalid token")

    email = data.get("email")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.email_verified = True
    db.commit()
    return {"message": "Email verified"}

# ---------------- Login / Logout ----------------
@router.post("/login")
async def login(
    req: Request,
    res: Response,
    payload: UserLogin,
    db: Session = Depends(get_db),
    code: str | None = None  # 2FA TOTP code if enabled (19)
):
    user = db.query(User).filter(User.email == payload.email).first()
    ip = _client_ip(req)

    if not user or user.status == "suspended":  # (24)
        db.add(LoginAttempt(user_id=None, ip_address=ip, success=False))
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid credentials")

    # Lockout check (10, 32)
    if user.lock_until and user.lock_until > datetime.utcnow():
        raise HTTPException(status_code=403, detail="Account locked. Try later or check email.")

    if not verify_password(payload.password, user.password_hash):
        user.login_attempts = (user.login_attempts or 0) + 1
        if user.login_attempts >= LOCKOUT_MAX_ATTEMPTS:
            user.lock_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_DURATION_MIN)
        db.add(LoginAttempt(user_id=user.id, ip_address=ip, success=False))
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid credentials")

    # Success → clear attempts, update last login (27, 31)
    user.login_attempts = 0
    user.last_login_at = datetime.utcnow()
    db.add(LoginAttempt(user_id=user.id, ip_address=ip, success=True))
    db.commit()

    # 2FA enforcement (19)
    if user.twofa_enabled and user.twofa_secret:
        if not code:
            raise HTTPException(status_code=206, detail="2FA required")
        if not pyotp.TOTP(user.twofa_secret).verify(code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid 2FA code")

    token = create_access_token({"sub": str(user.id)})
    # Secure cookie (8)
    res.set_cookie(key="access_token", value=token, httponly=True, secure=True, samesite="lax")
    return {"message": "Logged in", "user_id": user.id}

@router.post("/logout")
async def logout(res: Response):
    res.delete_cookie("access_token")
    return {"message": "Logged out"}

# ---------------- Password reset ----------------
@router.post("/password/reset/request")
async def password_reset_request(email: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    # To avoid user enumeration: always respond OK
    if user:
        token = serializer.dumps({"email": email}, salt="pwd-reset")
        link = f"/auth/password/reset/confirm?token={token}"
        send_email(email, "Password Reset", f"<p>Reset your password: <a href='{link}'>Reset</a> (expires in {TOKEN_EXPIRE_PASSWORD_RESET_MIN} min)</p>")
    return {"message": "If the email exists, a reset link was sent."}

@router.post("/password/reset/confirm")
async def password_reset_confirm(token: str, new_password: str, confirm_password: str, db: Session = Depends(get_db)):
    # (13) confirm match
    if new_password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    # (14) enforce strength
    if len(new_password) < 8 or not re.search(r"[A-Z]", new_password) or not re.search(r"[a-z]", new_password) or not re.search(r"\d", new_password) or not re.search(r"[^A-Za-z0-9]", new_password):
        raise HTTPException(status_code=400, detail="Weak password")

    try:
        data = serializer.loads(token, salt="pwd-reset", max_age=TOKEN_EXPIRE_PASSWORD_RESET_MIN * 60)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail="Reset token expired")
    except BadSignature:
        raise HTTPException(status_code=400, detail="Invalid token")

    email = data.get("email")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = get_password_hash(new_password)
    db.commit()
    return {"message": "Password updated"}

# ---------------- 2FA (TOTP) ----------------
@router.post("/2fa/enable")
async def enable_2fa(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.twofa_enabled:
        return {"message": "2FA already enabled"}
    secret = pyotp.random_base32()
    current_user.twofa_secret = secret
    current_user.twofa_enabled = True
    db.commit()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=current_user.email, issuer_name="Reputation SaaS")
    return {"otpauth_uri": uri}

@router.post("/2fa/verify")
async def verify_2fa(code: str, current_user: User = Depends(get_current_user)):
    if not current_user.twofa_enabled or not current_user.twofa_secret:
        raise HTTPException(status_code=400, detail="2FA not enabled")
    totp = pyotp.TOTP(current_user.twofa_secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid 2FA code")
    return {"message": "2FA verified"}

# ---------------- Unlock flow ----------------
@router.post("/unlock/request")
async def unlock_request(email: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if user:
        token = serializer.dumps({"email": email}, salt="unlock")
        link = f"/auth/unlock/confirm?token={token}"
        send_email(email, "Unlock your account", f"<p>Click to unlock: <a href='{link}'>Unlock</a></p>")
    return {"message": "If the account exists, an unlock link was sent."}

@router.get("/unlock/confirm")
async def unlock_confirm(token: str, db: Session = Depends(get_db)):
    try:
        data = serializer.loads(token, salt="unlock", max_age=3600)
        email = data.get("email")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid token")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.login_attempts = 0
    user.lock_until = None
    db.commit()
    return {"message": "Account unlocked"}

# ---------------- OAuth (Google) ----------------
from authlib.integrations.starlette_client import OAuth
from starlette.responses import RedirectResponse
from starlette.requests import Request as StarletteRequest

oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_OAUTH["client_id"],
    client_secret=GOOGLE_OAUTH["client_secret"],
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"}
)

@router.get("/oauth/google/login")
async def google_login(request: StarletteRequest):
    redirect_uri = GOOGLE_OAUTH["redirect_uri"]
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/oauth/google/callback")
async def google_callback(request: StarletteRequest, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo:
        userinfo = await oauth.google.parse_id_token(request, token)

    email = userinfo.get("email")
    sub = userinfo.get("sub")
    name = (userinfo.get("name") or "Google User")[:100]

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            full_name=name,
            email=email,
            password_hash=get_password_hash("oauth-" + sub),
            email_verified=True,
            oauth_provider="google",
            oauth_sub=sub
        )
        db.add(user); db.commit(); db.refresh(user)

    res = RedirectResponse("/")
    jwt_token = create_access_token({"sub": str(user.id)})
    res.set_cookie(key="access_token", value=jwt_token, httponly=True, secure=True, samesite="lax")
    return res
