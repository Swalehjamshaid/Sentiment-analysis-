# filename: app/main.py
import os
import logging
import secrets
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from markupsafe import Markup
from jinja2 import pass_context

# Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# Internal imports
from .db import init_db, get_db
from .models import Company, User, Review
from .services.rbac import get_current_user
from .context import common_context

# Routers
from .routes import auth, companies, reviews, reply, reports, dashboard as dashboard_module
from .routes.maps_routes import router as maps_router
from .routes.activity import router as activity_router
from .routes.insights import router as insights_router

# Services
from .services.metrics import build_kpi_for_dashboard, build_dashboard_charts
from .services.ai_insights import analyze_reviews
from .services.google_maps import sync_company_reviews   # FIXED IMPORT


# ─────────────────────────────────────────────────────────────
# PATH SETUP (ABSOLUTE, WORKS ON DOCKER/RAILWAY)
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
# LOGGING
# ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("review_saas")

# ─────────────────────────────────────────────────────────────
# LIFESPAN – INIT DB
# ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        logger.info("Database initialized.")
    except Exception as e:
        logger.exception("Database initialization failed: %s", e)
    yield


app = FastAPI(title="ReviewSaaS", lifespan=lifespan)

# ─────────────────────────────────────────────────────────────
# MIDDLEWARE
# ─────────────────────────────────────────────────────────────
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "supersecret"),
    session_cookie="session",
    max_age=86400 * 7,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        forwarded = request.headers.get("x-forwarded-proto", request.url.scheme)
        if os.getenv("FORCE_HTTPS", "0") == "1" and forwarded != "https":
            return RedirectResponse(request.url.replace(scheme="https"))
        return await call_next(request)


app.add_middleware(HTTPSRedirectMiddleware)

# ─────────────────────────────────────────────────────────────
# TEMPLATES CONFIG
# ─────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Jinja filters
def format_date(value, fmt="%Y-%m-%d"):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except:
            return value
    return value.strftime(fmt)


templates.env.filters["date"] = format_date
templates.env.globals["now"] = lambda: datetime.now(timezone.utc)


@pass_context
def csrf_token(ctx):
    req = ctx.get("request")
    if not req:
        return ""
    token = req.session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        req.session["_csrf"] = token
    return Markup(f'<input type="hidden" name="csrf_token" value="{token}">')


templates.env.globals["csrf_token"] = csrf_token


# ─────────────────────────────────────────────────────────────
# SAFE CONTEXT for templates (ALIGN WITH YOUR HTML)
# ─────────────────────────────────────────────────────────────
def get_safe_context(request: Request, current_user=None) -> Dict[str, Any]:
