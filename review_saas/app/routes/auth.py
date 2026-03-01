
# filename: app/routes/auth.py
from __future__ import annotations
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.templating import Jinja2Templates

from app.core.config import settings

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "title": "Login"})


@router.post("/login")
async def login_post(request: Request, email: str = Form(...), password: str = Form(...)):
    # Demo-only: accept any credentials
    request.session["user_id"] = email
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)
