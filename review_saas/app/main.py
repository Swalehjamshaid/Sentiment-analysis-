import os
import logging
from pathlib import Path
from typing import Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

# Internal relative imports
from .db import init_db
from .routes import auth, companies, reviews, reply, reports, dashboard, admin
from .routes.maps_routes import router as maps_router
from .routes.activity import router as activity_router
from .routes.insights import router as insights_router

# ───────────────────────────────────────────────────────────────
# PATH RESOLUTION (Railway Safe)
# ───────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Fallback for Railway nested mount cases
if not TEMPLATE_DIR.exists():
    TEMPLATE_DIR = PROJECT_ROOT / "app" / "templates"

# ───────────────────────────────────────────────────────────────
# Logging
# ───────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("review_saas")

logger.info(f"Base directory: {BASE_DIR}")
logger.info(f"Templates directory: {TEMPLATE_DIR}")
logger.info(f"Static directory: {STATIC_DIR}")

# ───────────────────────────────────────────────────────────────
# Settings fallback (safe)
# ───────────────────────────────────────────────────────────────

try:
    from .core.config import settings
except Exception:
    class _Settings:
        APP_NAME: str = "ReviewSaaS"
        FORCE_HTTPS: bool = bool(int(os.getenv("FORCE_HTTPS", "0")))
        CORS_ALLOW_ORIGINS: str = os.getenv("CORS_ALLOW_ORIGINS", "*")

    settings = _Settings()

# ───────────────────────────────────────────────────────────────
# Lifespan (Modern FastAPI Startup)
# ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    try:
        init_db(drop_existing=os.getenv("DROP_ALL_TABLES") == "1")
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database startup failed: {e}")
    yield
    logger.info("Application shutdown.")

# ───────────────────────────────────────────────────────────────
# FastAPI App
# ───────────────────────────────────────────────────────────────

app = FastAPI(
    title=getattr(settings, "APP_NAME", "ReviewSaaS"),
    lifespan=lifespan
)

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Mount static files safely
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    logger.info("Static files mounted.")

# Global template variables
templates.env.globals.update({
    "googleMapsKey": os.getenv("GOOGLE_MAPS_API_KEY", ""),
    "apiBase": "",
    "currentDate": "2026-02-24"
})

# ───────────────────────────────────────────────────────────────
# Middleware
# ───────────────────────────────────────────────────────────────

class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if getattr(settings, "FORCE_HTTPS", False) and proto != "https":
            url = request.url.replace(scheme="https")
            return RedirectResponse(url, status_code=307)
        return await call_next(request)

app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)

_allow_origins = getattr(settings, "CORS_ALLOW_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allow_origins.split(",")] if _allow_origins != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ───────────────────────────────────────────────────────────────
# Template Context
# ───────────────────────────────────────────────────────────────

def template_context(request: Request) -> Dict[str, Any]:
    return {
        "request": request,
        "current_user": {"name": "Huda", "id": 1},
        "apiBase": "",
        "googleMapsKey": os.getenv("GOOGLE_MAPS_API_KEY", ""),
    }

# ───────────────────────────────────────────────────────────────
# UI Routes
# ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(context: dict = Depends(template_context)):
    return templates.TemplateResponse("home.html", context)

@app.get("/login", response_class=HTMLResponse)
async def login_page(context: dict = Depends(template_context)):
    return templates.TemplateResponse("login.html", context)

# Removed duplicate /dashboard route since dashboard.router handles it
# If you still want a direct route, you can keep it, but ensure template name matches "dashboard.html"

# ───────────────────────────────────────────────────────────────
# Routers
# ───────────────────────────────────────────────────────────────

app.include_router(auth.router, prefix="/auth")
app.include_router(companies.router)
app.include_router(reviews.router)
app.include_router(dashboard.router)  # dashboard.html must exist inside templates
app.include_router(reports.router)
app.include_router(admin.router)
app.include_router(maps_router)
app.include_router(activity_router, prefix="/api/activity", tags=["telemetry"])
app.include_router(insights_router, prefix="/api/insights", tags=["ai"])

# ───────────────────────────────────────────────────────────────
# Health Check
# ───────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "date": "2026-02-24"
    }
