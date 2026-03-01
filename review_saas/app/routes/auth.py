# filename: app/routes/auth.py
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from ..core.db import get_db
from ..models.models import User

logger = logging.getLogger("app.auth")
router = APIRouter(tags=["Auth"])
templates = Jinja2Templates(directory="app/templates")

# --- HOLISTIC FIX: BCRYPT IDENT ---
# Adding bcrypt__ident="2b" explicitly solves the Python 3.13 backend discovery crash
pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto",
    bcrypt__ident="2b" 
)

# ---------- REGISTER PAGE ----------
@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, next: str | None = None):
    return templates.TemplateResponse("register.html", {
        "request": request,
        "next": next or "/dashboard"
    })

# ---------- REGISTER LOGIC (POST) ----------
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

    # 1. Validation: Password Match
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Passwords do not match.", 
            "full_name": full_name, "email": email, "next": next
        })

    # 2. Validation: Unique Email
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Email already exists.", 
            "full_name": full_name, "next": next
        })

    try:
        # 3. Logic: Hash and Save
        hashed = pwd_context.hash(password)
        new_user = User(
            full_name=full_name,
            email=email,
            password_hash=hashed,
            status="active"
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"New user registered successfully: {email}")
        return RedirectResponse(
            url=f"/login?message=Account created successfully! Please login.&next={next}", 
            status_code=302
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Registration failed: {str(e)}")
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Database error. Please try again.", 
            "full_name": full_name, "email": email, "next": next
        })

# ---------- LOGIN PAGE ----------
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str | None = None, message: str | None = None):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "next": next or "/dashboard",
        "message": message
    })

# ---------- LOGIN LOGIC (POST) ----------
@router.post("/login")
async def login_submit(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/dashboard")
):
    email = (email or "").strip().lower()
    
    # 1. Find User
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Invalid email or password", "next": next
        })

    # 2. Verify Password
    # Handles both potential naming conventions for safety
    stored_hash = getattr(user, "password_hash", None) or getattr(user, "hashed_password", None)
    
    if not stored_hash or not pwd_context.verify(password, stored_hash):
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Invalid email or password", "next": next
        })

    # 3. Session Management
    if "session" in request.scope:
        request.session["user_id"] = user.id
        request.session["user_email"] = user.email
        request.session["user_name"] = user.full_name

    return RedirectResponse(url=(next or "/dashboard"), status_code=302)

# ---------- LOGOUT ----------
@router.get("/logout")
async def logout(request: Request):
    if "session" in request.scope:
        request.session.clear()
    return RedirectResponse(url="/login?message=Logged out successfully", status_code=302)
