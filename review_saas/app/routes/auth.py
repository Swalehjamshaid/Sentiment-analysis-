# filename: review_saas/app/routes/auth.py
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import hashlib

from app.db import get_db
from app.models import User
from app.context import common_context

router = APIRouter()

def _hash(pw: str) -> str:
    # NOTE: for production use passlib/bcrypt. This is a simple placeholder.
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

@router.get("/register")
async def register_view(request: Request):
    ctx = common_context(request)
    return request.app.state.templates.TemplateResponse("register.html", ctx)  # templates injected in main.py

@router.post("/register")
async def register_post(
    request: Request,
    name: str = Form(""),
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    # CSRF
    if request.session.get("_csrf") != csrf_token:
        return RedirectResponse("/register?error=csrf", status_code=302)

    email = email.strip().lower()
    if not email or not password:
        request.session["flash_error"] = "Email and password are required."
        return RedirectResponse("/register", status_code=302)

    exists = db.query(User).filter(User.email == email).first()
    if exists:
        request.session["flash_error"] = "Email is already registered."
        return RedirectResponse("/register", status_code=302)

    u = User(name=name.strip() or None, email=email, password_hash=_hash(password))
    db.add(u)
    db.commit()

    request.session["flash_success"] = "Registration successful. Please sign in."
    return RedirectResponse("/login", status_code=302)

# This function is used by main.py /login POST
async def login_post(request: Request, email: str, password: str, db: Session):
    email = (email or "").strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    # Accept either hashed or plain (for compatibility with existing data)
    hashed = getattr(user, "password_hash", None)
    if hashed and hashed == _hash(password):
        return user
    # If existing DB used plain passwords (legacy), allow plain match too:
    if getattr(user, "password", None) and user.password == password:
        return user
    return None
