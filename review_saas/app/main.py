
# filename: app/main.py
from __future__ import annotations
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

from app.core.config import settings
from app.core.db import get_engine
from app.routes import auth as auth_routes
from app.routes import dashboard as dashboard_routes
from app.routes import companies as companies_routes

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

# CORS (open by default; restrict origins in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sessions
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie=settings.SESSION_COOKIE_NAME,
    same_site=settings.SESSION_COOKIE_SAMESITE,
    https_only=settings.SESSION_COOKIE_SECURE,
)

templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
async def on_startup():
    # Lazily create DB engine; will raise clear error if DATABASE_URL is invalid
    _ = get_engine()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # If logged in, go to dashboard
    if request.session.get("user_id"):
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("base.html", {"request": request, "title": settings.APP_NAME})


# Include route modules
app.include_router(auth_routes.router, prefix="")
app.include_router(dashboard_routes.router, prefix="")
app.include_router(companies_routes.router, prefix="")


# Simple health
@app.get("/health")
async def health():
    return {"status": "ok"}
