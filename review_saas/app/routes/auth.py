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

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")  # or switch to "argon2"

def get_password_hash(password: str) -> str:
    """Hash password safely with bcrypt (truncate at 72 bytes)"""
    max_bytes = 72
    encoded = password.encode("utf-8")
    if len(encoded) > max_bytes:
        encoded = encoded[:max_bytes]
    return pwd_context.hash(encoded.decode("utf-8"))

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
    profile: Optional[UploadFile] = File(None),  # optional profile picture
    db: Session = Depends(get_db),
):
    # Check if user exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash password safely
    hashed_password = get_password_hash(password)

    # Handle profile picture (optional)
    profile_pic_url = None
    if profile and profile.filename:
        # save file logic here
        filename = f"profile_{datetime.utcnow().timestamp()}_{profile.filename}"
        file_path = f"app/static/uploads/{filename}"
        with open(file_path, "wb") as f:
            f.write(await profile.read())
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
