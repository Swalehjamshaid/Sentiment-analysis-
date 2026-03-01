# File: app/main.py
from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# Absolute imports
from app.core.config import settings
from app.core.db import init_db
from app.models.base import Base
from app.routes import auth, companies, dashboard, exports, reports, admin
from app.services.scheduler import start_scheduler

# Structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger('review_saas')

# ─────────────────────────────────────────────
# LIFESPAN CONTEXT: Initialize DB & Scheduler
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    init_db(Base)
    try:
        start_scheduler()
        logger.info("Background scheduler active.")
    except Exception as e:
        logger.error(f"Scheduler failed to start: {e}")
    yield

# ─────────────────────────────────────────────
# APP INSTANCE
# ─────────────────────────────────────────────
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# ─────────────────────────────────────────────
# SESSION MIDDLEWARE
# ─────────────────────────────────────────────
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    same_site="lax",
    https_only=settings.COOKIE_SECURE
)

# ─────────────────────────────────────────────
# STATIC FILES & TEMPLATES
# ─────────────────────────────────────────────
STATIC_DIR = "app/static"
os.makedirs(os.path.join(STATIC_DIR, "uploads"), exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory='app/templates')

# ─────────────────────────────────────────────
# AUTHENTICATION HELPERS
# ─────────────────────────────────────────────
def is_authenticated(request: Request) -> bool:
    """Check if user is logged in via session only (no token)."""
    session = request.scope.get("session", {})
    return bool(session.get("user_id"))

# ─────────────────────────────────────────────
# REDIRECT MIDDLEWARE
# ─────────────────────────────────────────────
PROTECTED_PREFIXES = ("/dashboard", "/companies", "/reviews", "/reports", "/exports", "/admin")

@app.middleware("http")
async def auth_redirects(request: Request, call_next):
    """
    Handle user flow:
    - Logged out + protected path -> redirect to /login
    - Logged in + (/, /login, /register) -> redirect to /dashboard
    """
    path = request.url.path
    if path.startswith("/static") or path == "/google/health":
        return await call_next(request)

    authed = is_authenticated(request)

    # Redirect authenticated users away from login/register
    if authed and path in ("/", "/login", "/register"):
        return RedirectResponse(url="/dashboard", status_code=302)

    # Redirect unauthenticated users from protected paths
    if not authed and path.startswith(PROTECTED_PREFIXES):
        original = path
        if request.url.query:
            original += f"?{request.url.query}"
        next_param = quote(original, safe="")
        return RedirectResponse(url=f"/login?next={next_param}", status_code=302)

    return await call_next(request)

# ─────────────────────────────────────────────
# PUBLIC ROUTES
# ─────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Landing page with Login/Register options."""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": settings.APP_NAME
    })

@app.get("/google/health")
async def google_health():
    """Health check endpoint for monitoring."""
    return JSONResponse({"status": "healthy"})

# ─────────────────────────────────────────────
# INCLUDE ROUTERS
# ─────────────────────────────────────────────
app.include_router(auth.router)       # /login, /register (simple session-based registration)
app.include_router(dashboard.router)  # /dashboard
app.include_router(companies.router, prefix="/companies")
app.include_router(reviews.router, prefix="/reviews")
app.include_router(exports.router, prefix="/exports")
app.include_router(reports.router, prefix="/reports")
app.include_router(admin.router, prefix="/admin")
