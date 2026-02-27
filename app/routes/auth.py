
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User

router = APIRouter()
logger = logging.getLogger("auth")

def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

@router.get("/register")
async def register_view(request: Request):
    return RedirectResponse("/\?show=register", status_code=302)

@router.post("/register")
async def register_post(
    request: Request,
    name: str = Form(""),
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        sess_token = request.session.get("_csrf")
    except Exception:
        sess_token = None
    if not sess_token or csrf_token != sess_token:
        if "session" in request.scope:
            request.session["flash_error"] = "Security check failed. Please try again."
        logger.info("REGISTER FAIL: csrf mismatch")
        return RedirectResponse("/\?show=register", status_code=302)

    full_name = (name or "").strip()
    email_norm = (email or "").strip().lower()
    password_norm = (password or "").strip()

    if not email_norm or not password_norm:
        if "session" in request.scope:
            request.session["flash_error"] = "Email and password are required."
        return RedirectResponse("/\?show=register", status_code=302)

    exists = db.query(User).filter(User.email == email_norm).first()
    if exists:
        if "session" in request.scope:
            request.session["flash_error"] = "Email is already registered. Please sign in."
        return RedirectResponse("/\?show=login", status_code=302)

    try:
        user = User(
            full_name=full_name or "User",
            email=email_norm,
            password_hash=_hash(password_norm),
            status="active",
        )
        db.add(user)
        db.commit()
    except Exception as e:
        db.rollback()
        if "session" in request.scope:
            request.session["flash_error"] = "Unexpected error creating account. Please try again."
        return RedirectResponse("/\?show=register", status_code=302)

    if "session" in request.scope:
        request.session["flash_success"] = "Registration successful. Please sign in."
    return RedirectResponse("/\?show=login", status_code=302)

async def login_post(
    request: Request,
    email: str,
    password: str,
    db: Session,
) -> Optional[User]:
    original_email = email
    email_norm = (email or "").strip().lower()
    password_norm = (password or "").strip()

    if not email_norm or not password_norm:
        logger.info("LOGIN FAIL: missing email/password (email_in='%s')", original_email)
        return None

    user = db.query(User).filter(User.email == email_norm).first()
    if not user:
        logger.info("LOGIN FAIL: user not found email='%s'", email_norm)
        return None

    stored_hash = getattr(user, "password_hash", None)
    input_hash = _hash(password_norm)

    if stored_hash and stored_hash == input_hash:
        return user

    if getattr(user, "password", None) and user.password == password_norm:
        return user

    return None
