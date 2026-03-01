# File: app/main.py
from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

# Absolute imports
from app.core.settings import settings
from app.core.db import init_db
from app.models.models import Base
from app.routes import auth, companies, reviews, dashboard, exports, reports, admin
from app.services.scheduler import start_scheduler

# Structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("review_saas")

# ────────────────────────────────────────────────
# LIFESPAN / APP INITIALIZATION
# ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup / shutdown lifecycle:
    - Initialize database
    - Start background scheduler for review fetching / PDF generation
    """
    logger.info("Initializing database...")
    init_db(Base)
    try:
        start_scheduler()
        logger.info("Background scheduler active.")
    except Exception as e:
        logger.error(f"Scheduler failed to start: {e}")
    yield
    logger.info("Shutting down FastAPI app...")

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# ────────────────────────────────────────────────
# SESSION MIDDLEWARE (secure HTTP-only cookies recommended in production)
# ────────────────────────────────────────────────
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    same_site="lax",
    https_only=False,  # True in production with HTTPS
)

# ────────────────────────────────────────────────
# STATIC FILES & TEMPLATES
# ────────────────────────────────────────────────
STATIC_DIR = "app/static"
os.makedirs(os.path.join(STATIC_DIR, "uploads"), exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory="app/templates")

# ────────────────────────────────────────────────
# AUTHENTICATION HELPERS
# ────────────────────────────────────────────────
def is_authenticated(request: Request) -> bool:
    """
    Returns True if user is logged in:
    - Session-based
    - Optional token-based (JWT / OAuth)
    """
    session = request.scope.get("session", {})
    return bool(session.get("user_id") or request.cookies.get("access_token"))

# ────────────────────────────────────────────────
# REDIRECT / AUTH MIDDLEWARE
# ────────────────────────────────────────────────
PROTECTED_PREFIXES = (
    "/dashboard",
    "/companies",
    "/reviews",
    "/reports",
    "/exports",
    "/admin",
)

@app.middleware("http")
async def auth_redirects(request: Request, call_next):
    """
    Handles:
    - Logged out users trying to access protected routes -> redirect to /login
    - Logged in users trying to access /, /login, /register -> redirect to /dashboard
    """
    path = request.url.path
    if path.startswith("/static") or path == "/google/health":
        return await call_next(request)

    authed = is_authenticated(request)

    if authed and path in ("/", "/login", "/register"):
        return RedirectResponse(url="/dashboard", status_code=302)

    if not authed and path.startswith(PROTECTED_PREFIXES):
        original = path
        if request.url.query:
            original += f"?{request.url.query}"
        next_param = quote(original, safe="")
        return RedirectResponse(url=f"/login?next={next_param}", status_code=302)

    return await call_next(request)

# ────────────────────────────────────────────────
# PUBLIC ROUTES
# ────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Landing page for SaaS with Login / Register options."""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": settings.APP_NAME,
    })

@app.get("/google/health")
async def google_health():
    return JSONResponse({"status": "healthy"})

# ────────────────────────────────────────────────
# ROUTERS
# ────────────────────────────────────────────────
# User Authentication (Login, Register, OAuth, Password Reset)
app.include_router(auth.router)

# Dashboard & Metrics (KPIs, charts, recent reviews)
app.include_router(dashboard.router)

# Companies CRUD + validation + Google Places integration
app.include_router(companies.router, prefix="/companies")

# Review fetching, storing, sentiment analysis
app.include_router(reviews.router, prefix="/reviews")

# Exports (CSV / Excel)
app.include_router(exports.router, prefix="/exports")

# Reports (PDF generation / scheduling)
app.include_router(reports.router, prefix="/reports")

# Admin Panel (optional / view all users & companies)
app.include_router(admin.router, prefix="/admin")

# ────────────────────────────────────────────────
# OPTIONAL FEATURES HOOKS (for future integration)
# ────────────────────────────────────────────────
# - 2FA via email/SMS/app
# - OAuth Login (Google / Facebook / LinkedIn)
# - Notifications for negative reviews or KPI alerts
# - Scheduled automatic PDF reports
# - Multi-language support
# - Multi-source review tracking (Facebook, Yelp, TripAdvisor)

logger.info(f"{settings.APP_NAME} app initialized successfully.")
