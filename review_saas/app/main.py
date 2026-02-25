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
from .models import Company
from .services.rbac import get_current_user
from .context import common_context  # decoupled context to prevent circular imports
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

# Fallback for containerized environments
if not TEMPLATE_DIR.exists():
    TEMPLATE_DIR = PROJECT_ROOT / "app" / "templates"
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
    max_age=3600 * 24 * 7  # 1 week
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
# Templates
# ─────────────────────────────────────────────────────────────

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Custom Jinja2 filters and globals
def format_date(value, fmt="%b %d, %Y"):
    if value is None:
        return ""
    mapping = {
        'Y-m-d': '%Y-%m-%d',
        'd-m-Y': '%d-%m-%Y',
        'H:i': '%H:%M',
        'M d, Y': '%b %d, %Y'
    }
    fmt = mapping.get(fmt, fmt)

    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
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

# Static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ─────────────────────────────────────────────────────────────
# WebSocket: Dashboard
# ─────────────────────────────────────────────────────────────

@app.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("home.html", common_context(request))

@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    if get_current_user(request):
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse("login.html", common_context(request))

@app.post("/login")
async def login_post(request: Request, email: str = Form(...), password: str = Form(...)):
    return await auth.login_post(request, email, password, next(get_db()))

# Include routers
app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(reviews.router)
app.include_router(reply.router)
app.include_router(reports.router)
app.include_router(dashboard.router)
app.include_router(maps_router)
app.include_router(activity_router, prefix="/api/activity", tags=["telemetry"])
app.include_router(insights_router, prefix="/api/insights", tags=["ai"])

# Health check
@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.APP_NAME}
