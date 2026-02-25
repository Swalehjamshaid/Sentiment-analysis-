# FILE: app/main.py

import os
import logging
from pathlib import Path
from typing import Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

# Internal modules
from .db import init_db, get_db
from .models import Company

# Correct user loader (fixed)
from .services.rbac import get_current_user

# Routers
from .routes import auth, companies, reviews, reply, reports, dashboard, admin
from .routes.maps_routes import router as maps_router
from .routes.activity import router as activity_router
from .routes.insights import router as insights_router

# WebSocket manager
from .dependencies import manager


# ------------------------------------------------------------------------------
# PATHS
# ------------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

if not TEMPLATE_DIR.exists():   # fallback for deployments
    TEMPLATE_DIR = PROJECT_ROOT / "app" / "templates"
    STATIC_DIR = PROJECT_ROOT / "app" / "static"


# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("review_saas")


# ------------------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------------------
class Settings:
    APP_NAME = "ReviewSaaS"
    FORCE_HTTPS = bool(int(os.getenv("FORCE_HTTPS", "0")))
    CORS_ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "*")

    # Load from environment (no hard‑coding)
    GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_KEY", "")

settings = Settings()


# ------------------------------------------------------------------------------
# LIFESPAN
# ------------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")

    try:
        init_db(drop_existing=os.getenv("DROP_ALL_TABLES") == "1")
        logger.info("Database sync complete.")
    except Exception as e:
        logger.error(f"DB init error: {e}")

    yield


# ------------------------------------------------------------------------------
# FASTAPI APP
# ------------------------------------------------------------------------------
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)


# ------------------------------------------------------------------------------
# Middleware Stack
# ------------------------------------------------------------------------------
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "supersecretkey123"),
)

class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        if settings.FORCE_HTTPS and scheme != "https":
            return RedirectResponse(request.url.replace(scheme="https"), status_code=307)
        return await call_next(request)

app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.CORS_ALLOW_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ------------------------------------------------------------------------------
# Templates & Static
# ------------------------------------------------------------------------------
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ------------------------------------------------------------------------------
# COMMON CONTEXT (FIXED FOR AUTH)
# ------------------------------------------------------------------------------
def common_context(request: Request) -> Dict[str, Any]:
    """
    Central context provider used by all pages.
    Includes:
    - current_user from secure session-based RBAC
    - global company list
    - google maps key
    - environment metadata
    """

    # Use session‑aware RBAC loader
    try:
        user = get_current_user(request)
    except Exception:
        user = None

    # DB fetch
    db = next(get_db())
    try:
        companies_list = db.query(Company).order_by(Company.name.asc()).all()
    except Exception as e:
        logger.error(f"Failed fetching company switcher data: {e}")
        companies_list = []
    finally:
        db.close()

    return {
        "request": request,
        "current_user": user,
        "is_authenticated": user is not None,
        "companies": companies_list,
        "googleMapsKey": settings.GOOGLE_MAPS_KEY,
        "apiBase": "",
    }


# ------------------------------------------------------------------------------
# WebSocket Endpoint
# ------------------------------------------------------------------------------
@app.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    """ Real-time dashboard updates """
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ------------------------------------------------------------------------------
# PAGE ROUTES
# ------------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("home.html", common_context(request))


@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    if get_current_user(request):
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse("login.html", common_context(request))


# ------------------------------------------------------------------------------
# API ROUTES
# ------------------------------------------------------------------------------
app.include_router(auth.router, prefix="/auth")
app.include_router(companies.router)
app.include_router(reviews.router)
app.include_router(reply.router)
app.include_router(reports.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
app.include_router(maps_router)
app.include_router(activity_router, prefix="/api/activity", tags=["telemetry"])
app.include_router(insights_router, prefix="/api/insights", tags=["ai"])


# ------------------------------------------------------------------------------
# Health Check
# ------------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "date": "2026-02-25"
    }
