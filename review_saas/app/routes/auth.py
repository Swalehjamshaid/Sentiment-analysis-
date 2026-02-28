# Filename: review_saas/app/routes/auth.py

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.db import get_db
from app.models import User
from passlib.context import CryptContext
from datetime import datetime
from fastapi.templating import Jinja2Templates
import unicodedata
import os

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Use bcrypt_sha256 to safely handle arbitrarily long passwords.
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    default="bcrypt_sha256",
    deprecated="auto",
)

# Directory to save uploaded profile images
UPLOAD_DIR = "app/static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _normalize_password(password: str) -> str:
    """Normalize Unicode so different codepoint forms of the same visual password hash identically."""
    return unicodedata.normalize("NFKC", password)


def get_password_hash(password: str) -> str:
    """Hash password safely using bcrypt_sha256."""
    normalized = _normalize_password(password)
    return pwd_context.hash(normalized)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a stored hash."""
    normalized = _normalize_password(plain_password)
    return pwd_context.verify(normalized, hashed_password)


# --- GET route to serve registration page ---
@router.get("/register", response_class=HTMLResponse)
async def get_register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


# --- POST route to handle registration ---
@router.post("/register")
async def register(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    profile: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    if len(password.encode("utf-8")) > 4096:
        raise HTTPException(status_code=400, detail="Password too long")

    hashed_password = get_password_hash(password)

    profile_pic_url = None
    if profile and profile.filename:
        timestamp = int(datetime.utcnow().timestamp())
        filename = f"profile_{timestamp}_{profile.filename}"
        file_path = os.path.join(UPLOAD_DIR, filename)
        content = await profile.read()
        with open(file_path, "wb") as f:
            f.write(content)
        profile_pic_url = f"/static/uploads/{filename}"

    new_user = User(
        full_name=full_name,
        email=email,
        password_hash=hashed_password,
        profile_pic_url=profile_pic_url,
        status="active",
        created_at=datetime.utcnow(),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "id": new_user.id,
        "full_name": new_user.full_name,
        "email": new_user.email,
        "profile_pic_url": new_user.profile_pic_url,
        "status": new_user.status,
    }


# --- GET route to serve login page ---
@router.get("/login", response_class=HTMLResponse)
async def get_login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


# --- POST route to handle login ---
@router.post("/login")
async def login(
    email: str = Form(...),
    password: str = Form(...),
    totp: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return JSONResponse({"error": "Invalid credentials"}, status_code=400)

    if not verify_password(password, user.password_hash):
        return JSONResponse({"error": "Invalid credentials"}, status_code=400)

    # For now, skipping actual 2FA validation
    # Could implement totp verification here if needed

    # Simulate access token for frontend storage
    access_token = f"dummy-token-for-user-{user.id}"

    return JSONResponse({"access_token": access_token, "token_type": "bearer"})
