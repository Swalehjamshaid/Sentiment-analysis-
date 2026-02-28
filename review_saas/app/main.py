# File: review_saas/app/main.py
from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

# Absolute imports to ensure Uvicorn finds the modules correctly
from app.core.settings import settings
from app.core.db import init_db
from app.models.base import Base
from app.routes import auth, companies, reviews, dashboard, exports, reports, admin
from app.services.scheduler import start_scheduler

# Requirement #130: Structured Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger('review_saas')

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database and Scheduler
    logger.info('Initializing database...')
    init_db(Base)
    try:
        start_scheduler()
        logger.info('Background scheduler active.')
    except Exception as e:
        logger.error(f'Scheduler failed to start: {e}')
    yield

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# --- Session Middleware (required for login state) ---
SECRET = getattr(settings, "SECRET_KEY", None) or os.getenv("SECRET_KEY") or "dev-secret"
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET,
    same_site="lax",     # keeps auth stable while allowing dashboard to load assets
    https_only=False     # set True in production with HTTPS
)

# --- Static Files & Directory Safety ---
STATIC_DIR = "app/static"
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")

for path in [STATIC_DIR, UPLOAD_DIR]:
    if not os.path.exists(path):
        logger.info(f"Creating missing directory: {path}")
        os.makedirs(path, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory='app/templates')

# ------------ Auth Utilities & Redirect Middleware ------------

def is_authenticated(request: Request) -> bool:
    """
    Returns True if the user is considered logged in.
    We support either:
      - Session-based login: request.session['user_id'] or request.session['user']
      - Token-based login: a cookie named 'access_token'
    Adjust keys to match your auth implementation if needed.
    """
    s = getattr(request, "session", {}) or {}
    return bool(
        s.get("user_id") or s.get("user") or request.cookies.get("access_token")
    )

# Routes that should require authentication (redirect to /login if not logged in)
PROTECTED_PREFIXES = (
    "/dashboard", "/companies", "/reviews", "/reports", "/exports", "/admin"
)

@app.middleware("http")
async def auth_redirects(request: Request, call_next):
    """
    Global middleware to enforce the desired flow:

    - If user is NOT authenticated and visits a PROTECTED route,
      redirect them to /login?next=<original>.

    - If user IS authenticated and visits '/', '/login', or '/register',
      redirect them to '/dashboard'.

    - /static and other assets bypass checks.
    """
    path = request.url.path or "/"

    # Allow static assets without checks
    if path.startswith("/static"):
        return await call_next(request)

    authed = is_authenticated(request)

    # Authenticated users shouldn't see login/register again
    if authed and path in ("/", "/login", "/register"):
        return RedirectResponse(url="/dashboard", status_code=302)

    # Unauthenticated users cannot access protected areas
    if not authed and path.startswith(PROTECTED_PREFIXES):
        # Preserve the original path + query string to return after login
        original = path
        if request.url.query:
            original += f"?{request.url.query}"
        next_param = quote(original, safe="")
        return RedirectResponse(url=f"/login?next={next_param}", status_code=302)

    return await call_next(request)

# ------------ Routes ------------

@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    """
    Landing page (public). If you prefer '/', to immediately open login instead of index,
    you can replace this response with a RedirectResponse('/login').
    """
    return templates.TemplateResponse('index.html', {
        'request': request,
        'title': settings.APP_NAME
    })

# --- Registering Routers ---
# These routers should provide:
#   - GET /login (render login page)
#   - POST /login (perform auth; set session/cookie; redirect to ?next or /dashboard)
#   - GET /register (render register page)
#   - POST /register (create user; optionally auto-login + redirect to /dashboard)
app.include_router(auth.router)
app.include_router(companies.router, prefix="/companies")
app.include_router(reviews.router, prefix="/reviews")
app.include_router(dashboard.router, prefix="/dashboard")
app.include_router(exports.router, prefix="/exports")
app.include_router(reports.router, prefix="/reports")
app.include_router(admin.router, prefix="/admin")
