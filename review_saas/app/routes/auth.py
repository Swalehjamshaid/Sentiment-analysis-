# filename: review_saas/app/routes/auth.py
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


# ────────────────────────────────────────────────────────────────
# Password Hashing (keep same algorithm you used at register)
# ────────────────────────────────────────────────────────────────
def _hash(pw: str) -> str:
    """
    NOTE: For production, use passlib / bcrypt or argon2id.
    Here we must keep SHA-256 to match existing stored password_hash.
    """
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


# ────────────────────────────────────────────────────────────────
# Views (Register opens via modal)
# ────────────────────────────────────────────────────────────────
@router.get("/register")
async def register_view(request: Request):
    """
    UI uses base page modal; so just redirect with query string.
    """
    return RedirectResponse("/?show=register", status_code=302)


# ────────────────────────────────────────────────────────────────
# Register (creates the user with SHA-256 hash)
# ────────────────────────────────────────────────────────────────
@router.post("/register")
async def register_post(
    request: Request,
    name: str = Form(""),
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Creates a new user (full_name, email, password_hash).
    Requires CSRF token stored in session['_csrf'] by main.py.
    """
    # 1) CSRF check — only if session exists
    try:
        sess_token = request.session.get("_csrf")  # SessionMiddleware is installed in main.py
    except Exception:
        sess_token = None

    if not sess_token or csrf_token != sess_token:
        if "session" in request.scope:
            request.session["flash_error"] = "Security check failed. Please try again."
        logger.info("REGISTER FAIL: csrf mismatch (session=%s, form=%s)", bool(sess_token), bool(csrf_token))
        return RedirectResponse("/?show=register", status_code=302)

    # 2) Normalize inputs
    full_name = (name or "").strip()
    email_in = (email or "").strip()
    email_norm = email_in.lower()

    # 3) Validate
    if not email_norm or not password:
        if "session" in request.scope:
            request.session["flash_error"] = "Email and password are required."
        logger.info("REGISTER FAIL: missing email or password")
        return RedirectResponse("/?show=register", status_code=302)

    # 4) Check for existing user
    exists = db.query(User).filter(User.email == email_norm).first()
    if exists:
        if "session" in request.scope:
            request.session["flash_error"] = "Email is already registered. Please sign in."
        logger.info("REGISTER INFO: email already registered: %s", email_norm)
        return RedirectResponse("/?show=login", status_code=302)

    # 5) Create user
    try:
        user = User(
            full_name=full_name or "User",
            email=email_norm,
            password_hash=_hash(password),
            status="active",
        )
        db.add(user)
        db.commit()
        logger.info("REGISTER OK: user_id=%s email=%s", user.id, user.email)
    except Exception as e:
        db.rollback()
        logger.exception("REGISTER ERROR: DB commit failed: %s", e)
        if "session" in request.scope:
            request.session["flash_error"] = "Unexpected error creating account. Please try again."
        return RedirectResponse("/?show=register", status_code=302)

    # 6) Success → open Login modal
    if "session" in request.scope:
        request.session["flash_success"] = "Registration successful. Please sign in."
    return RedirectResponse("/?show=login", status_code=302)


# ────────────────────────────────────────────────────────────────
# LOGIN HELPER (called by /login POST in main.py)
# ────────────────────────────────────────────────────────────────
async def login_post(
    request: Request,
    email: str,
    password: str,
    db: Session,
) -> Optional[User]:
    """
    Lookup user by normalized email and verify password against stored SHA-256.
    Returns user on success; None otherwise.
    """
    original_email = email
    email_norm = (email or "").strip().lower()

    if not email_norm or not password:
        logger.info("LOGIN FAIL: missing email/password (email_in='%s')", original_email)
        return None

    user = db.query(User).filter(User.email == email_norm).first()
    if not user:
        logger.info("LOGIN FAIL: user not found email='%s' (original='%s')", email_norm, original_email)
        return None

    stored_hash = getattr(user, "password_hash", None)
    input_hash = _hash(password)

    if stored_hash and stored_hash == input_hash:
        logger.info("LOGIN OK: user_id=%s email=%s", user.id, user.email)
        return user

    # Legacy compatibility: accept plain-text password field if present
    if getattr(user, "password", None) and user.password == password:
        logger.info("LOGIN OK (legacy plain): user_id=%s email=%s", user.id, user.email)
        return user

    logger.info("LOGIN FAIL: hash mismatch user_id=%s email=%s", user.id, user.email)
    return None


# ────────────────────────────────────────────────────────────────
# Optional: whoami helper (useful for debugging session)
# ────────────────────────────────────────────────────────────────
@router.get("/me")
async def whoami(request: Request):
    """
    Returns session snapshot (for debugging only). Remove in production.
    """
    try:
        data = {
            "has_session": "session" in request.scope,
            "session_keys": list(request.session.keys()) if "session" in request.scope else [],
            "user_id": request.session.get("user_id") if "session" in request.scope else None,
            "user_email": request.session.get("user_email") if "session" in request.scope else None,
            "user_name": request.session.get("user_name") if "session" in request.scope else None,
        }
    except Exception:
        data = {"has_session": False}
    return data
