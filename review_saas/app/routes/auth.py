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

# Fixed for Python 3.13: Explicitly define the bcrypt identifier
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__ident="2b")

@router.post("/register")
async def register_submit(
    request: Request,
    db: Session = Depends(get_db),
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):
    email = (email or "").strip().lower()
    
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Passwords do not match."})

    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse("register.html", {"request": request, "error": "Email already registered."})

    try:
        new_user = User(
            full_name=full_name,
            email=email,
            password_hash=pwd_context.hash(password),
            status="active"
        )
        db.add(new_user)
        db.commit()
        return RedirectResponse(url="/login?message=Registration+successful!", status_code=302)
    except Exception as e:
        db.rollback()
        logger.error(f"Registration failed: {e}")
        return templates.TemplateResponse("register.html", {"request": request, "error": "Internal database error."})

@router.post("/login")
async def login_submit(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...)
):
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not pwd_context.verify(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials."})

    request.session["user_id"] = user.id
    request.session["user_name"] = user.full_name
    return RedirectResponse(url="/dashboard", status_code=302)
