# File: app/main.py
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

# Internal imports
from .db import init_db, get_db
from .models import Company
from .routes import auth, companies, reviews, reply, reports, dashboard, admin
from .routes.maps_routes import router as maps_router
from .routes.activity import router as activity_router
from .routes.insights import router as insights_router

# Import shared dependencies
from .dependencies import get_current_user, manager

# ───────────────────────────────────────────────────────────────
# PATH RESOLUTION
# ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

if not TEMPLATE_DIR.exists():
    TEMPLATE_DIR = PROJECT_ROOT / "app" / "templates"
    STATIC_DIR = PROJECT_ROOT / "app" / "static"

# ───────────────────────────────────────────────────────────────
# Logging & Settings
# ───────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("review_saas")

class _Settings:
    APP_NAME: str = "ReviewSaaS"
    FORCE_HTTPS: bool = bool(int(os.getenv("FORCE_HTTPS", "0")))
    CORS_ALLOW_ORIGINS: str = os.getenv("CORS_ALLOW_ORIGINS", "*")
    # Using your provided production keys
    GOOGLE_MAPS_KEY: str = "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg"

settings = _Settings()

# ───────────────────────────────────────────────────────────────
# Lifespan
# ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    try:
        init_db(drop_existing=os.getenv("DROP_ALL_TABLES") == "1")
    except Exception as e:
        logger.error(f"Database startup failed: {e}")
    yield

# ───────────────────────────────────────────────────────────────
# FastAPI App & Middleware
# ───────────────────────────────────────────────────────────────
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecretkey123"))

class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if settings.FORCE_HTTPS and proto != "https":
            url = request.url.replace(scheme="https")
            return RedirectResponse(url, status_code=307)
        return await call_next(request)

app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, 
                   allow_origins=[settings.CORS_ALLOW_ORIGINS], 
                   allow_credentials=True, 
                   allow_methods=["*"], 
                   allow_headers=["*"])

# ───────────────────────────────────────────────────────────────
# Templates & Static
# ───────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

def common_context(request: Request) -> Dict[str, Any]:
    """
    World-class context provider. Fetches current user and 
    existing companies to populate the UI globally.
    """
    user = get_current_user(request)
    
    # Create a temporary DB session to fetch company list for the switcher
    db = next(get_db())
    try:
        companies_list = db.query(Company).order_by(Company.name).all()
    except Exception as e:
        logger.error(f"Context company fetch failed: {e}")
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
        "currentDate": "2026-02-24",
    }

# ───────────────────────────────────────────────────────────────
# WebSocket Endpoint
# ───────────────────────────────────────────────────────────────
@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    """
    Handles real-time updates for the dashboard sync process.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ───────────────────────────────────────────────────────────────
# Routes
# ───────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("home.html", common_context(request))

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("login.html", common_context(request))

# Include Routers
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
    return {"status": "healthy", "service": "ReviewSaaS", "date": "2026-02-24"}
