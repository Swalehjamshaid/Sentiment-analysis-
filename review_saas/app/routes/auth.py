# app/routers/auth.py
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, constr
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
import secrets, re

from ..db import get_db, User  # Stub DB models

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "YOUR_SECRET_KEY"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

class RegisterUser(BaseModel):
    full_name: constr(min_length=2, max_length=100)
    email: EmailStr
    password: constr(min_length=8)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

def validate_password(password: str):
    regex = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&]).{8,}$'
    if not re.match(regex, password):
        raise HTTPException(status_code=400, detail="Password must include uppercase, lowercase, number, special char, min 8 chars")

@router.post("/register", response_model=dict)
async def register_user(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    file: UploadFile | None = File(None),
    db = Depends(get_db)
):
    validate_password(password)
    if await User.get_by_email(db, email):
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = pwd_context.hash(password)
    profile_url = None
    if file:
        if file.content_type not in ["image/jpeg", "image/png"]:
            raise HTTPException(status_code=400, detail="Invalid image type")
        profile_url = f"/uploads/{secrets.token_hex(8)}_{file.filename}"
    user = await User.create(db, full_name, email, hashed_password, profile_url)
    verification_token = secrets.token_urlsafe(32)
    await User.save_verification_token(db, user.id, verification_token)
    return {"message": "User registered. Please verify your email."}

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    user = await User.get_by_email(db, form_data.username)
    if not user or not pwd_context.verify(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account is locked or inactive")
    access_token = jwt.encode({"sub": user.email, "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/reset-request")
async def password_reset_request(email: EmailStr = Form(...), db=Depends(get_db)):
    user = await User.get_by_email(db, email)
    if user:
        token = secrets.token_urlsafe(32)
        await User.save_reset_token(db, user.id, token)
    return {"message": "If email exists, reset link sent."}

@router.post("/reset-password")
async def reset_password(token: str = Form(...), password: str = Form(...), db=Depends(get_db)):
    validate_password(password)
    user = await User.get_by_reset_token(db, token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    hashed_password = pwd_context.hash(password)
    await User.update_password(db, user.id, hashed_password)
    return {"message": "Password reset successful"}

@router.get("/verify-email")
async def verify_email(token: str, db=Depends(get_db)):
    user = await User.verify_email_token(db, token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    return {"message": "Email verified successfully"}
