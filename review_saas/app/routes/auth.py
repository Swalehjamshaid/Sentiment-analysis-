# File: app/routes/auth.py
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from ..core.db import get_db
from ..models.models import User

logger = logging.getLogger("app.auth")
router = APIRouter(tags=["Auth"])
templates = Jinja2Templates(directory="app/templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------- REGISTER ----------
@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, next: str | None = None):
    return templates.TemplateResponse("register.html", {
        "request": request,
        "next": next or "/dashboard"
    })

@router.post("/register")
async def register_submit(
    request: Request,
    db: Session = Depends(get_db),
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    next: str = Form("/dashboard")
):
    email = (email or "").strip().lower()
    full_name = (full_name or "").strip()

    if password != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Passwords do not match.",
            "next": next,
            "full_name": full_name,
            "email": email
        }, status_code=400)

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "An account with this email already exists.",
            "next": next,
            "full_name": full_name,
            "email": email
        }, status_code=400)

    # Create user
    hashed = pwd_context.hash(password)
    user = User(email=email)
    
    # Robustly set attributes based on your model field names
    for attr in ["full_name", "name"]:
        if hasattr(user, attr):
            setattr(user, attr, full_name)
    
    for attr in ["hashed_password", "password_hash"]:
        if hasattr(user, attr):
            setattr(user, attr, hashed)

    db.add(user)
    db.commit()
    db.refresh(user)

    # Logic: Redirect to login with a success message instead of auto-logging in
    return RedirectResponse(
        url=f"/login?message=Registration successful! Please login.&next={next}", 
        status_code=302
    )

# ---------- LOGIN ----------
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str | None = None, message: str | None = None):
    # This grabs the "message" from the URL if it exists (like after registration)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "next": next or "/dashboard",
        "message": message
    })

@router.post("/login")
async def login_submit(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/dashboard")
):
    email = (email or "").strip().lower()
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Invalid email or password", "next": next
        }, status_code=400)

    hashed = getattr(user, "hashed_password", None) or getattr(user, "password_hash", None)
    
    try:
        ok = pwd_context.verify(password, hashed)
    except Exception:
        ok = False

    if not ok:
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Invalid email or password", "next": next
        }, status_code=400)

    # Set session
    if "session" in request.scope:
        request.session["user_id"] = user.id
        request.session["user_email"] = user.email

    # Redirect directly to dashboard
    return RedirectResponse(url=(next or "/dashboard"), status_code=302)

# ---------- LOGOUT ----------
@router.get("/logout")
async def logout(request: Request):
    if "session" in request.scope:
        request.session.clear()
    return RedirectResponse(url="/login?message=Logged out successfully", status_code=302)
