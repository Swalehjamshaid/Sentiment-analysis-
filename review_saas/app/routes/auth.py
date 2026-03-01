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

    # Basic validations
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Passwords do not match.",
            "next": next,
            "full_name": full_name,
            "email": email
        }, status_code=400)

    # Email uniqueness
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
    user = User(email=email)  # set name/full_name robustly
    if hasattr(user, "full_name"):
        user.full_name = full_name
    elif hasattr(user, "name"):
        user.name = full_name
    if hasattr(user, "hashed_password"):
        user.hashed_password = hashed
    else:
        # Fallback if model uses a different field name (very rare)
        setattr(user, "password_hash", hashed)

    db.add(user)
    db.commit()
    db.refresh(user)

    # Auto-login via session
    if "session" in request.scope:
        request.session["user_id"] = user.id

    return RedirectResponse(url=(next or "/dashboard"), status_code=302)

# ---------- LOGIN ----------
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str | None = None):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "next": next or "/dashboard"
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

    if "session" in request.scope:
        request.session["user_id"] = user.id

    return RedirectResponse(url=(next or "/dashboard"), status_code=302)

# ---------- LOGOUT ----------
@router.get("/logout")
async def logout(request: Request):
    if "session" in request.scope:
        request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
