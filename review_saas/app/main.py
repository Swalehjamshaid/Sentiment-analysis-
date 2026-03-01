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

# Absolute imports
from app.core.settings import settings
from app.core.db import init_db
from app.models.base import Base
from app.routes import auth, companies, reviews, dashboard, exports, reports, admin
from app.services.scheduler import start_scheduler

# Structured Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger('review_saas')

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('Initializing database...')
    init_db(Base)
    try:
        start_scheduler()
        logger.info('Background scheduler active.')
    except Exception as e:
        logger.error(f'Scheduler failed to start: {e}')
    yield

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# --- 1. SESSION MIDDLEWARE (Must be added BEFORE the custom redirect middleware) ---
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    same_site="lax",
    https_only=False  # Set True in production with HTTPS
)

# --- Static Files & Templates ---
STATIC_DIR = "app/static"
os.makedirs(os.path.join(STATIC_DIR, "uploads"), exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory='app/templates')

# --- 2. AUTHENTICATION HELPERS ---
def is_authenticated(request: Request) -> bool:
    """Checks if user is logged in via session safely."""
    # Using request.scope.get prevents the AssertionError if middleware hasn't run
    session = request.scope.get("session", {})
    return bool(session.get("user_id") or request.cookies.get("access_token"))

# --- 3. REDIRECT MIDDLEWARE ---
PROTECTED_PREFIXES = ("/dashboard", "/companies", "/reviews", "/reports", "/exports", "/admin")

@app.middleware("http")
async def auth_redirects(request: Request, call_next):
    """
    Handles user flow:
    - Logged out + Protected path -> /login
    - Logged in + (/, /login, /register) -> /dashboard
    """
    path = request.url.path
    
    if path.startswith("/static") or path == "/google/health":
        return await call_next(request)

    authed = is_authenticated(request)

    # If Authed, prevent access to Login/Register/Landing
    if authed and path in ("/", "/login", "/register"):
        return RedirectResponse(url="/dashboard", status_code=302)

    # If Not Authed, prevent access to Dashboard/Settings
    if not authed and path.startswith(PROTECTED_PREFIXES):
        original = path
        if request.url.query:
            original += f"?{request.url.query}"
        next_param = quote(original, safe="")
        return RedirectResponse(url=f"/login?next={next_param}", status_code=302)

    return await call_next(request)

# --- 4. PUBLIC ROUTES ---

@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    """Public landing page with Login/Register options."""
    return templates.TemplateResponse('index.html', {
        'request': request, 
        'title': settings.APP_NAME
    })

@app.get("/google/health")
async def google_health():
    return JSONResponse({"status": "healthy"})

# --- 5. REGISTER ROUTERS ---
app.include_router(auth.router)     # Handles POST /login and POST /register
app.include_router(dashboard.router) # Should define @router.get("/dashboard")
app.include_router(companies.router, prefix="/companies")
app.include_router(reviews.router, prefix="/reviews")
app.include_router(exports.router, prefix="/exports")
app.include_router(reports.router, prefix="/reports")
app.include_router(admin.router, prefix="/admin")
