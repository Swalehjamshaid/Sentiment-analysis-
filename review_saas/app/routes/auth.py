# app/routers/auth.py
import re
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import jwt, secrets, base64, os
from ..db import get_db
from ..models import User
from ..utils.email_utils import send_verification_email, send_password_reset_email
from ..utils.google_api import verify_google_oauth_token

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET = os.environ.get("JWT_SECRET")
JWT_ALG = os.environ.get("JWT_ALG", "HS256")
LOCKOUT_THRESHOLD = int(os.environ.get("LOCKOUT_THRESHOLD", 5))
LOCKOUT_MINUTES = int(os.environ.get("LOCKOUT_MINUTES", 15))
VERIFY_TOKEN_HOURS = int(os.environ.get("VERIFY_TOKEN_HOURS", 24))
RESET_TOKEN_MINUTES = int(os.environ.get("RESET_TOKEN_MINUTES", 30))


def hash_password(password: str):
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str):
    return pwd_context.verify(password, hashed)


def validate_password_strength(password: str):
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False
    return True


@router.post("/register")
async def register(
    full_name: str = Form(..., max_length=100),
    email: str = Form(...),
    password: str = Form(...),
    profile_picture: UploadFile | None = None,
    db: Session = Depends(get_db)
):
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    if not validate_password_strength(password):
        raise HTTPException(status_code=400, detail="Password does not meet complexity requirements")

    hashed_pw = hash_password(password)
    verification_token = secrets.token_urlsafe(32)
    token_expiry = datetime.utcnow() + timedelta(hours=VERIFY_TOKEN_HOURS)

    user = User(
        full_name=full_name,
        email=email,
        password_hash=hashed_pw,
        profile_picture_url=None,
        account_status="inactive",
        verification_token=verification_token,
        verification_expiry=token_expiry,
        created_at=datetime.utcnow()
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    await send_verification_email(user.email, verification_token)
    return {"message": "Registration successful. Please check your email to verify your account."}


@router.post("/login")
async def login(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Lockout logic
    # TODO: Implement failed login tracking

    token = jwt.encode(
        {"user_id": user.id, "exp": datetime.utcnow() + timedelta(minutes=120)},
        JWT_SECRET, algorithm=JWT_ALG
    )
    return {"access_token": token, "token_type": "bearer"}


@router.get("/verify-email/{token}")
async def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.verification_token == token).first()
    if not user or user.verification_expiry < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    user.account_status = "active"
    user.verification_token = None
    db.commit()
    return {"message": "Email verified successfully"}


@router.post("/password-reset-request")
async def password_reset_request(email: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return JSONResponse({"message": "If the email exists, a reset link has been sent."})
    
    reset_token = secrets.token_urlsafe(32)
    user.reset_token = reset_token
    user.reset_token_expiry = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_MINUTES)
    db.commit()

    await send_password_reset_email(email, reset_token)
    return {"message": "Password reset link sent via email."}


@router.post("/password-reset")
async def password_reset(token: str = Form(...), new_password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.reset_token == token).first()
    if not user or user.reset_token_expiry < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    if not validate_password_strength(new_password):
        raise HTTPException(status_code=400, detail="Password does not meet complexity requirements")
    user.password_hash = hash_password(new_password)
    user.reset_token = None
    db.commit()
    return {"message": "Password reset successful"}


@router.get("/google-oauth-callback")
async def google_oauth_callback(code: str):
    access_token = await verify_google_oauth_token(code)
    return {"access_token": access_token}
