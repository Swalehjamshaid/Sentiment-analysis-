# File: app/main.py

from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.db import init_db
from app.models.base import Base
from app.routes import auth, companies, reviews, dashboard, exports, reports, admin
from app.services.scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("review_saas")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    init_db(Base)
    try:
        start_scheduler()
        logger.info("Background scheduler active.")
    except Exception as e:
        logger.error(f"Scheduler failed to start: {e}")
    yield

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

ACCESS_TOKEN_MIN = int(os.getenv("ACCESS_TOKEN_MIN", "120"))

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("JWT_SECRET", "supersecretkey"),
    max_age=ACCESS_TOKEN_MIN * 60,
    same_site="lax",
    https_only=os.getenv("COOKIE_SECURE", "true").lower() == "true",
    session_cookie=os.getenv("COOKIE_DOMAIN", "sentiment-analysis-production-ca50.up.railway.app")
)

STATIC_DIR = "app/static"
os.makedirs(os.path.join(STATIC_DIR, "uploads"), exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory="app/templates")

def is_authenticated(request: Request) -> bool:
    session = request.scope.get("session", {})
    return bool(session.get("user_id") or request.cookies.get("access_token"))

PROTECTED_PREFIXES = (
    "/dashboard", "/companies", "/reviews",
    "/reports", "/exports", "/admin"
)

@app.middleware("http")
async def auth_redirects(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path == "/google/health":
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

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": settings.APP_NAME}
    )

@app.get("/google/health")
async def google_health():
    return JSONResponse({"status": "healthy"})

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(companies.router, prefix="/companies")
app.include_router(reviews.router, prefix="/reviews")
app.include_router(exports.router, prefix="/exports")
app.include_router(reports.router, prefix="/reports")
app.include_router(admin.router, prefix="/admin")

app.state.google_business_key = os.getenv("GOOGLE_BUSINESS_API_KEY", "")
app.state.google_maps_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
app.state.google_places_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
app.state.app_base_url = os.getenv("APP_BASE_URL", "https://sentiment-analysis-production-ca50.up.railway.app")
app.state.jwt_alg = os.getenv("JWT_ALG", "HS256")
app.state.jwt_secret = os.getenv("JWT_SECRET", "supersecretkey")
app.state.lockout_minutes = int(os.getenv("LOCKOUT_MINUTES", "30"))
app.state.lockout_threshold = int(os.getenv("LOCKOUT_THRESHOLD", "5"))
app.state.oauth_google_client_id = os.getenv("OAUTH_GOOGLE_CLIENT_ID", "")
app.state.oauth_google_client_secret = os.getenv("OAUTH_GOOGLE_CLIENT_SECRET", "")
app.state.oauth_google_redirect_uri = os.getenv("OAUTH_GOOGLE_REDIRECT_URI", "")
