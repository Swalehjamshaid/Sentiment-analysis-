# Filename: app/routes/auth.py

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
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
# Keep "bcrypt" in the scheme list to verify existing legacy hashes and allow seamless migration.
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],  # order matters: first is default
    default="bcrypt_sha256",
    deprecated="auto",
)

# Directory to save uploaded profile images
UPLOAD_DIR = "app/static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _normalize_password(password: str) -> str:
    """
    Normalize Unicode so different codepoint forms of the same visual password hash identically.
    """
    return unicodedata.normalize("NFKC", password)


def get_password_hash(password: str) -> str:
    """
    Hash password safely using bcrypt_sha256 (sha256 -> bcrypt).
    This avoids bcrypt's 72-byte limit without truncation.
    """
    normalized = _normalize_password(password)
    return pwd_context.hash(normalized)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a stored hash (supports both bcrypt_sha256 and legacy bcrypt).
    """
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
    # Check if user exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Optional: enforce a sane upper bound to prevent pathological input sizes (UX guard, not a security requirement)
    if len(password.encode("utf-8")) > 4096:
        raise HTTPException(status_code=400, detail="Password too long")

    # Hash password safely (no manual truncation)
    hashed_password = get_password_hash(password)

    # Handle profile picture (optional)
    profile_pic_url = None
    if profile and profile.filename:
        timestamp = int(datetime.utcnow().timestamp())
        # Basic sanitization of filename could be added here if needed
        filename = f"profile_{timestamp}_{profile.filename}"
        file_path = os.path.join(UPLOAD_DIR, filename)
        # Read the file content once and write it to disk
        content = await profile.read()
        with open(file_path, "wb") as f:
            f.write(content)
        profile_pic_url = f"/static/uploads/{filename}"

    # Create user
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
