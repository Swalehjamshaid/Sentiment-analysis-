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

# -------------------------------
# Core imports
# -------------------------------
from app.core.config import settings
from app.core.db import init_db  # database engine initializer
from app.models.base import Base  # SQLAlchemy Base

# -------------------------------
# Routes
# -------------------------------
from app.routes import auth, companies, dashboard
# Other routes can be added later: reviews, reports, exports, admin

# -------------------------------
# Services
# -------------------------------
from app.services.scheduler import start_scheduler
# from app.services.google_api import GoogleAPI   # optional Google integration
# from app.services.sentiment import analyze_sentiment  # optional AI logic

# -------------------------------
# Logging
# -------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("review_saas")

# -------------------------------
# Lifespan: DB Init + Scheduler
# -------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    try:
        init_db(Base)
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    try:
        start_scheduler()
        logger.info("Background scheduler started successfully.")
    except Exception as e:
        logger.error(f"Scheduler failed to start: {e}")
    yield

# -------------------------------
# FastAPI App Instance
# -------------------------------
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# -------------------------------
# Session Middleware
# -------------------------------
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    same_site="lax",
    https_only=settings.COOKIE_SECURE
)

# -------------------------------
# Static Files & Templates
# -------------------------------
STATIC_DIR = "app/static"
os.makedirs(os.path.join(STATIC_DIR, "uploads"), exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory="app/templates")

# -------------------------------
# Auth helper
# -------------------------------
def is_authenticated(request: Request) -> bool:
    """Check if user session exists."""
    return bool(request.session.get("user_id"))

# -------------------------------
# Auth redirect middleware
# -------------------------------
PROTECTED_PREFIXES = ("/dashboard", "/companies", "/reviews", "/reports", "/exports", "/admin")

@app.middleware("http")
async def auth_redirects(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path == "/google/health":
        return await call_next(request)

    authed = is_authenticated(request)

    # Redirect logged-in users away from login/register
    if authed and path in ("/", "/login", "/register"):
        return RedirectResponse("/dashboard", status_code=302)

    # Redirect unauthenticated users from protected paths
    if not authed and path.startswith(PROTECTED_PREFIXES):
        original = path
        if request.url.query:
            original += f"?{request.url.query}"
        next_param = quote(original, safe="")
        return RedirectResponse(url=f"/login?next={next_param}", status_code=302)

    return await call_next(request)

# -------------------------------
# Public routes
# -------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": settings.APP_NAME
    })

@app.get("/google/health")
async def google_health():
    """Health check endpoint"""
    return JSONResponse({"status": "healthy"})

# -------------------------------
# Include routers
# -------------------------------
app.include_router(auth.router)        # /login, /register
app.include_router(dashboard.router)   # /dashboard
app.include_router(companies.router, prefix="/companies")
# Add additional routers as needed:
# app.include_router(reviews.router, prefix="/reviews")
# app.include_router(exports.router, prefix="/exports")
# app.include_router(reports.router, prefix="/reports")
# app.include_router(admin.router, prefix="/admin")
