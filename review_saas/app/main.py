import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

# Internal relative imports
from .db import engine, init_db
from .models import Base, Company
from .routes import auth, companies, reviews, reply, reports, dashboard, admin
from .routes.maps_routes import router as maps_router
from .routes.activity import router as activity_router
from .routes.insights import router as insights_router

# ───────────────────────────────────────────────────────────────
# Path Discovery (Fixes "Template NOT FOUND")
# ───────────────────────────────────────────────────────────────
# This finds the actual folder on the Railway disk
BASE_DIR = Path(__file__).resolve().parent 
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Logger Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")
logger.info(f"Templates Path Resolved to: {TEMPLATE_DIR}")

# Configuration fallback logic
try:
    from .core.config import settings
except Exception:
    class _Settings:
        APP_NAME: str = "ReviewSaaS"
        FORCE_HTTPS: bool = bool(int(os.getenv("FORCE_HTTPS", "0")))
        CORS_ALLOW_ORIGINS: str = os.getenv("CORS_ALLOW_ORIGINS", "*")
    settings = _Settings()

# HTTPS Redirect Middleware
class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if getattr(settings, "FORCE_HTTPS", False) and proto != "https":
            url = request.url.replace(scheme="https")
            return RedirectResponse(url, status_code=307)
        return await call_next(request)

# ───────────────────────────────────────────────────────────────
# FastAPI app initialization
# ───────────────────────────────────────────────────────────────
app = FastAPI(title=getattr(settings, "APP_NAME", "ReviewSaaS"))

# Mount Static Files (using absolute path)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount Uploads (usually in the root or a dedicated volume)
if os.path.isdir("app_uploads"):
    app.mount("/uploads", StaticFiles(directory="app_uploads"), name="uploads")

# Initialize Templates with the Absolute Path
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Global Template Variables
templates.env.globals["googleMapsKey"] = os.getenv(
    "GOOGLE_MAPS_API_KEY", 
    "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg"
)
templates.env.globals["apiBase"] = ""
templates.env.globals["currentDate"] = "2026-02-24"

# Middlewares
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
# Database Initialization
# ───────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    logger.info("Initializing database...")
    try:
        init_db(drop_existing=os.getenv("DROP_ALL_TABLES") == "1")
        if os.getenv("RECREATE_COMPANIES") == "1":
            Base.metadata.drop_all(bind=engine, tables=[Company.__table__])
            Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.error(f"Database startup failed: {e}")

# ───────────────────────────────────────────────────────────────
# UI & API Routes
# ───────────────────────────────────────────────────────────────
def template_context(request: Request) -> Dict[str, Any]:
    return {
        "request": request,
        "current_user": {"name": "Huda", "id": 1},
        "apiBase": "",
        "googleMapsKey": os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg"),
    }

@app.get("/", response_class=HTMLResponse)
async def home(context: dict = Depends(template_context)):
    return templates.TemplateResponse("home.html", context)

@app.get("/login", response_class=HTMLResponse)
async def login_page(context: dict = Depends(template_context)):
    return templates.TemplateResponse("login.html", context)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(context: dict = Depends(template_context)):
    # This now looks in the absolute path resolved at startup
    return templates.TemplateResponse("dashbord.html", context)

app.include_router(auth.router, prefix="/auth")
app.include_router(companies.router)
app.include_router(reviews.router)
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(admin.router)
app.include_router(maps_router)
app.include_router(activity_router, prefix="/api/activity", tags=["telemetry"])
app.include_router(insights_router, prefix="/api/insights", tags=["ai"])

@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.APP_NAME, "date": "2026-02-24"}
