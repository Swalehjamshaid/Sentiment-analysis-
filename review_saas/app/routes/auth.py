# File: review_saas/app/routes/auth.py
from __future__ import annotations
import logging
from urllib.parse import urlencode
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
    # 1) Find user
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid email or password",
            "next": next
        }, status_code=400)

    # 2) Verify password
    try:
        ok = pwd_context.verify(password, user.hashed_password)
    except Exception:
        ok = False

    if not ok:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid email or password",
            "next": next
        }, status_code=400)

    # 3) Set session (PURE SESSION-BASED LOGIN)
    if "session" in request.scope:
        request.session["user_id"] = user.id

    # 4) Redirect
    return RedirectResponse(url=(next or "/dashboard"), status_code=302)

@router.get("/logout")
async def logout(request: Request):
    if "session" in request.scope:
        request.session.clear()
    resp = RedirectResponse(url="/login", status_code=302)
    # In case you later add tokens, clear them here (currently none used)
    return resp
