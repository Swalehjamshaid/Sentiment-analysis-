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

# Fixed: Explicitly using bcrypt with passlib to avoid the 500 error
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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

    # 1. Logic: Validate password match
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Passwords do not match.", "full_name": full_name, "email": email
        })

    # 2. Logic: Ensure unique email in Postgres
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Email already exists.", "full_name": full_name
        })

    # 3. Logic: Hash and Save (Matching your Railway Table Columns)
    hashed = pwd_context.hash(password)
    new_user = User(
        full_name=full_name,     # Matches column 'full_name'
        email=email,             # Matches column 'email'
        password_hash=hashed,    # Matches column 'password_hash'
        status="active"          # Matches column 'status'
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Redirect to login so they can verify their credentials
    return RedirectResponse(url=f"/login?message=Account created! Please login.&next={next}", status_code=302)

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
    
    # 1. Logic: Find user by email
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Invalid email or password", "next": next
        })

    # 2. Logic: Verify the password against the stored hash
    # Uses getattr to handle both 'password_hash' and 'hashed_password' safely
    stored_hash = getattr(user, "password_hash", None) or getattr(user, "hashed_password", None)
    
    if not pwd_context.verify(password, stored_hash):
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Invalid email or password", "next": next
        })

    # 3. Logic: Establish session (Recognized by main.py middleware)
    if "session" in request.scope:
        request.session["user_id"] = user.id
        request.session["user_email"] = user.email

    # Redirect to dashboard
    return RedirectResponse(url=(next or "/dashboard"), status_code=302)

# ---------- LOGOUT ----------
@router.get("/logout")
async def logout(request: Request):
    if "session" in request.scope:
        request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
