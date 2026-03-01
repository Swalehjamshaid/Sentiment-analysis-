# File: app/main.py
from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import quote
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

# 1. Load Settings First
from app.core.settings import settings
# 2. Then Load DB and Models
from app.core.db import init_db
from app.models.base import Base
# 3. Then Load Routers
from app.routes import auth, companies, reviews, dashboard, exports, reports, admin
from app.services.scheduler import start_scheduler

import googlemaps
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger('review_saas')

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('Initializing database...')
    init_db(Base)
    _init_google_clients(app)
    try:
        start_scheduler()
        logger.info('Background scheduler active.')
    except Exception as e:
        logger.error(f'Scheduler failed to start: {e}')
    yield

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# Middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    same_site="lax",
    https_only=False
)

# Static & Templates
STATIC_DIR = "app/static"
os.makedirs(os.path.join(STATIC_DIR, "uploads"), exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory='app/templates')

# Google Client Helper
def _init_google_clients(app: FastAPI) -> None:
    if settings.GOOGLE_MAPS_API_KEY:
        app.state.google_maps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)
    
    sa_file = settings.GOOGLE_SERVICE_ACCOUNT_FILE
    if sa_file and os.path.exists(sa_file):
        creds = service_account.Credentials.from_service_account_file(sa_file)
        app.state.google_biz_info = build("mybusinessbusinessinformation", "v1", credentials=creds)

# Auth Middleware logic
def is_authenticated(request: Request) -> bool:
    session = getattr(request, "session", {})
    return bool(session.get("user_id") or request.cookies.get("access_token"))

PROTECTED_PREFIXES = ("/dashboard", "/companies", "/reviews", "/reports", "/exports", "/admin")

@app.middleware("http")
async def auth_redirects(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path == "/google/health":
        return await call_next(request)

    authed = is_authenticated(request)
    if authed and path in ("/", "/login", "/register"):
        return RedirectResponse(url="/dashboard", status_code=302)
    if not authed and path.startswith(PROTECTED_PREFIXES):
        next_param = quote(str(request.url), safe="")
        return RedirectResponse(url=f"/login?next={next_param}", status_code=302)
    return await call_next(request)

# Main Routes
@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    if is_authenticated(request):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse('index.html', {'request': request, 'title': settings.APP_NAME})

@app.get("/google/health")
async def google_health(request: Request):
    return JSONResponse({"status": "healthy", "maps": bool(getattr(request.app.state, "google_maps", None))})

# Register Routers
app.include_router(auth.router)
app.include_router(dashboard.router) # No prefix to avoid /dashboard/dashboard
app.include_router(companies.router, prefix="/companies")
app.include_router(reviews.router, prefix="/reviews")
app.include_router(exports.router, prefix="/exports")
app.include_router(reports.router, prefix="/reports")
app.include_router(admin.router, prefix="/admin")
