# FILE: app/main.py

import os
import logging
from pathlib import Path
from typing import Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import secrets

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from markupsafe import Markup

from .db import init_db, get_db
from .models import Company, User
from .services.rbac import get_current_user
from .context import common_context
from .routes import auth, companies, reviews, reply, reports, dashboard
from .routes.maps_routes import router as maps_router
from .routes.activity import router as activity_router
from .routes.insights import router as insights_router
from .dependencies import manager

# ─────────────────────────────────────────────────────────────
# Paths & Directories
# ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

if not TEMPLATE_DIR.exists():
    TEMPLATE_DIR = PROJECT_ROOT / "app" / "templates"
if not STATIC_DIR.exists():
    STATIC_DIR = PROJECT_ROOT / "app" / "static"

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("review_saas")

# ─────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────
class Settings:
    APP_NAME: str = "ReviewSaaS"
    FORCE_HTTPS: bool = bool(int(os.getenv("FORCE_HTTPS", "0")))
    CORS_ALLOW_ORIGINS: str = os.getenv("CORS_ALLOW_ORIGINS", "*")
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", secrets.token_urlsafe(32))

settings = Settings()

# ─────────────────────────────────────────────────────────────
# Lifespan / Startup
# ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db(drop_existing=os.getenv("DROP_ALL_TABLES") == "1")
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.exception("Database initialization failed: %s", e)
    yield
    logger.info("Application shutting down.")

# ─────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# ─────────────────────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────────────────────
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET,
    session_cookie="session",
    max_age=3600 * 24 * 7
)

class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        if settings.FORCE_HTTPS and scheme != "https":
            url = request.url.replace(scheme="https")
            return RedirectResponse(url, status_code=307)
        return await call_next(request)

app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.CORS_ALLOW_ORIGINS] if settings.CORS_ALLOW_ORIGINS != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# ─────────────────────────────────────────────────────────────
# Templates & Static Files
# ─────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

def format_date(value, fmt="%b %d, %Y"):
    if value is None:
        return ""
    mapping = {'Y-m-d': '%Y-%m-%d', 'd-m-Y': '%d-%m-%Y', 'H:i': '%H:%M', 'M d, Y': '%b %d, %Y'}
    fmt = mapping.get(fmt, fmt)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except:
            return value
    return value.strftime(fmt)

def _now():
    return datetime.now(timezone.utc)

def _get_or_set_csrf(request: Request) -> str:
    token = request.session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["_csrf"] = token
    return token

def _csrf_token(request: Request):
    token = _get_or_set_csrf(request)
    return Markup(f'<input type="hidden" name="csrf_token" value="{token}">')

templates.env.filters["date"] = format_date
templates.env.globals["now"] = _now
templates.env.globals["csrf_token"] = _csrf_token

# ─────────────────────────────────────────────────────────────
# Helper: Safe Context Generator
# ─────────────────────────────────────────────────────────────
def get_safe_context(request: Request, current_user=None) -> dict:
    """Provides a consistent set of keys for dashboard.html rendering."""
    ctx = common_context(request)
    ctx.update({
        "current_user": current_user,
        "companies": [],
        "selected_company": None,
        "params": {"from": "", "to": "", "range": ""},
        "kpi": {"avg_rating": 0, "review_count": 0, "sentiment_score": 0, "growth": "0%"},
        "charts": {"labels": [], "sentiment": [], "rating": []},
        "reviews": [],
        "summary": "Please login or add a company to see insights.",
        "api_health": [],
        "alerts": [],
        "roles": []
    })
    return ctx

# ─────────────────────────────────────────────────────────────
# Local Routes
# ─────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse("dashboard.html", get_safe_context(request, user))

@app.get("/login", response_class=HTMLResponse)
async def login_view(request: Request): 
    if get_current_user(request):
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse("dashboard.html", get_safe_context(request))

@app.post("/login")
async def login_post(request: Request, email: str = Form(...), password: str = Form(...)):
    db = next(get_db())
    user = await auth.login_post(request, email, password, db)

    if user:
        request.session["user_id"] = user.id
        # Safety check for roles
        if user.roles:
            return RedirectResponse(f"/dashboard/{user.roles[0].company.id}", status_code=302)
        return RedirectResponse("/dashboard", status_code=302)
    else:
        context = get_safe_context(request)
        context["flash_error"] = "Invalid email or password."
        return templates.TemplateResponse("dashboard.html", context)

@app.get("/dashboard/{company_id}", response_class=HTMLResponse)
async def dashboard_view(request: Request, company_id: int): 
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")

    selected_company = next((r.company for r in user.roles if r.company.id == company_id), None)
    if not selected_company:
        context = get_safe_context(request, user)
        context["flash_error"] = f"No access to company ID {company_id}"
        return templates.TemplateResponse("dashboard.html", context)

    # Note: Full data dashboard should ideally be handled by dashboard.router
    # But for this local view, we provide a safe fallback:
    context = get_safe_context(request, user)
    context["selected_company"] = selected_company
    return templates.TemplateResponse("dashboard.html", context)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")

# ─────────────────────────────────────────────────────────────
# Include all routers
# ─────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(reviews.router)
app.include_router(reply.router)
app.include_router(reports.router)
app.include_router(dashboard.router) 
app.include_router(maps_router)
app.include_router(activity_router, prefix="/api/activity", tags=["telemetry"])
app.include_router(insights_router, prefix="/api/insights", tags=["ai"])

@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.APP_NAME}
