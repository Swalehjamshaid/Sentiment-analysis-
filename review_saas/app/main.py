# File: review_saas/app/main.py
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

# Absolute imports to ensure Uvicorn finds the modules correctly
from app.core.settings import settings
from app.core.db import init_db
from app.models.base import Base
from app.routes import auth, companies, reviews, dashboard, exports, reports, admin
from app.services.scheduler import start_scheduler

# ---- Google libraries ----
# requirements: googlemaps, google-api-python-client, google-auth, google-auth-oauthlib, google-auth-httplib2
import googlemaps
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.auth.transport.requests import Request as GoogleAuthRequest

# Requirement #130: Structured Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger('review_saas')


# ------------ Lifespan (startup/shutdown) ------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database
    logger.info('Initializing database...')
    init_db(Base)

    # Startup: Initialize Google clients
    _init_google_clients(app)

    # Startup: Scheduler
    try:
        start_scheduler()
        logger.info('Background scheduler active.')
    except Exception as e:
        logger.error(f'Scheduler failed to start: {e}')

    yield
    # (Optional) shutdown logic if needed later


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# --- Session Middleware (required for login state) ---
SECRET = getattr(settings, "SECRET_KEY", None) or os.getenv("SECRET_KEY") or "dev-secret"
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET,
    same_site="lax",
    https_only=False  # set True in production with HTTPS
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


# ------------ Google Initialization Helpers ------------
def _init_google_clients(app: FastAPI) -> None:
    """
    Initialize Google Maps client and Google API (Service Account) clients.
    Store them under app.state for DI usage in routers/services.
    """
    # ---- Google Maps (Places/Geocoding) ----
    maps_key = getattr(settings, "GOOGLE_MAPS_API_KEY", None) or os.getenv("GOOGLE_MAPS_API_KEY")
    if maps_key:
        try:
            app.state.google_maps: Optional[googlemaps.Client] = googlemaps.Client(key=maps_key)
            logger.info("Google Maps client initialized.")
        except Exception as e:
            app.state.google_maps = None
            logger.error(f"Failed to initialize Google Maps client: {e}")
    else:
        app.state.google_maps = None
        logger.warning("GOOGLE_MAPS_API_KEY not set. Google Maps features disabled.")

    # ---- Google Service Account (for Google APIs via discovery) ----
    # Common Business Profile scopes; add/remove as needed for your app:
    default_scopes = [
        "https://www.googleapis.com/auth/business.manage",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        # Add Sheets/Gmail scopes later if you integrate them
        # "https://www.googleapis.com/auth/spreadsheets",
        # "https://www.googleapis.com/auth/gmail.send",
    ]

    sa_file = (
        getattr(settings, "GOOGLE_SERVICE_ACCOUNT_FILE", None)
        or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")  # Google standard env var
    )
    scopes = getattr(settings, "GOOGLE_SCOPES", None) or os.getenv("GOOGLE_SCOPES")
    scopes_list = [s.strip() for s in scopes.split(",")] if isinstance(scopes, str) and scopes.strip() else default_scopes

    if sa_file and os.path.exists(sa_file):
        try:
            creds = service_account.Credentials.from_service_account_file(sa_file, scopes=scopes_list)

            # Refresh if needed (in case of long-lived container)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(GoogleAuthRequest())

            # Example Google API clients you may need:
            # Business Profile (Account Management):
            try:
                app.state.google_biz_account_mgmt = build("mybusinessaccountmanagement", "v1", credentials=creds, cache_discovery=False)
                logger.info("Google My Business Account Management client initialized.")
            except Exception as e:
                app.state.google_biz_account_mgmt = None
                logger.warning(f"Could not init mybusinessaccountmanagement: {e}")

            # Business Profile (Business Information):
            try:
                app.state.google_biz_info = build("mybusinessbusinessinformation", "v1", credentials=creds, cache_discovery=False)
                logger.info("Google My Business Business Information client initialized.")
            except Exception as e:
                app.state.google_biz_info = None
                logger.warning(f"Could not init mybusinessbusinessinformation: {e}")

            # Add other APIs as needed, e.g., Sheets:
            # app.state.google_sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)

            app.state.google_service_account_creds = creds
        except Exception as e:
            app.state.google_biz_account_mgmt = None
            app.state.google_biz_info = None
            app.state.google_service_account_creds = None
            logger.error(f"Failed to initialize Google Service Account credentials/clients: {e}")
    else:
        app.state.google_biz_account_mgmt = None
        app.state.google_biz_info = None
        app.state.google_service_account_creds = None
        logger.warning("Service Account credentials not found. Discovery-based Google APIs disabled.")


# ------------ Auth Utilities & Redirect Middleware ------------
def _get_session_if_available(request: Request):
    """Safely returns session dict if SessionMiddleware attached it to scope."""
    try:
        if "session" in request.scope:
            return request.session
    except AssertionError:
        return None
    return None

def is_authenticated(request: Request) -> bool:
    """Check if user is logged in via session or auth cookie."""
    session = _get_session_if_available(request) or {}
    return bool(session.get("user_id") or session.get("user") or request.cookies.get("access_token"))

# Routes that should require authentication
PROTECTED_PREFIXES = ("/dashboard", "/companies", "/reviews", "/reports", "/exports", "/admin")

@app.middleware("http")
async def auth_redirects(request: Request, call_next):
    """
    - Unauthed + PROTECTED → /login?next=...
    - Authed + (/, /login, /register) → /dashboard
    - Static bypasses checks.
    """
    path = request.url.path or "/"

    if path.startswith("/static"):
        return await call_next(request)

    authed = is_authenticated(request)

    if authed and path in ("/", "/login", "/register"):
        return RedirectResponse(url="/dashboard", status_code=302)

    if not authed and path.startswith(PROTECTED_PREFIXES):
        original = path
        if request.url.query:
            original += f"?{request.url.query}"
        next_param = quote(original, safe="")
        return RedirectResponse(url=f"/login?next={next_param}", status_code=302)

    return await call_next(request)


# ------------ Routes ------------
@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    """Public landing. You may redirect to /login if you prefer."""
    return templates.TemplateResponse('index.html', {'request': request, 'title': settings.APP_NAME})


@app.get("/google/health")
async def google_health(request: Request):
    """
    Lightweight health/config check for Google integrations.
    Avoids heavy outbound calls to keep startup snappy.
    """
    gm_ok = bool(getattr(request.app.state, "google_maps", None))
    sa_ok = bool(getattr(request.app.state, "google_service_account_creds", None))
    biz_mgmt_ok = bool(getattr(request.app.state, "google_biz_account_mgmt", None))
    biz_info_ok = bool(getattr(request.app.state, "google_biz_info", None))

    # Optional: perform a tiny live call to validate Maps key (commented by default)
    # try:
    #     if gm_ok:
    #         request.app.state.google_maps.geocode("Lahore, Pakistan")
    # except Exception as e:
    #     gm_ok = False
    #     logger.warning(f"Google Maps live check failed: {e}")

    return JSONResponse({
        "google_maps_configured": gm_ok,
        "service_account_configured": sa_ok,
        "business_profile_account_mgmt_client": biz_mgmt_ok,
        "business_profile_info_client": biz_info_ok
    })


# --- Registering Routers (existing project structure) ---
app.include_router(auth.router)
app.include_router(companies.router, prefix="/companies")
app.include_router(reviews.router, prefix="/reviews")
app.include_router(dashboard.router, prefix="/dashboard")
app.include_router(exports.router, prefix="/exports")
app.include_router(reports.router, prefix="/reports")
app.include_router(admin.router, prefix="/admin")
