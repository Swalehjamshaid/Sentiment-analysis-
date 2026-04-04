# filename: app/main.py
from __future__ import annotations
import os
import sys
import logging
import secrets
import resend
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
import httpx

# ------------------------------------------------------------------------------
# 0. SENTRY - Early initialization
# ------------------------------------------------------------------------------
try:
    import sentry_sdk
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    import logging as std_logging

    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        integrations=[
            AsyncioIntegration(),
            LoggingIntegration(level=std_logging.INFO, event_level=std_logging.ERROR),
        ],
        traces_sample_rate=0.1,
        environment=os.getenv("ENVIRONMENT", "production"),
    )
    logging.info("✅ Sentry initialized")
except Exception as e:
    logging.error("❌ Sentry init failed", exc_info=True)

# ------------------------------------------------------------------------------
# 1. MODULE & PATH RESOLUTION (Improved for templates)
# ------------------------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)

if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

def resolve_path(folder_name: str) -> str:
    """Improved path resolution with logging."""
    local_path = os.path.join(CURRENT_DIR, folder_name)
    parent_path = os.path.join(PARENT_DIR, folder_name)
    
    if os.path.exists(local_path):
        logging.info(f"✅ Using templates/static from: {local_path}")
        return local_path
    elif os.path.exists(parent_path):
        logging.info(f"✅ Using templates/static from: {parent_path}")
        return parent_path
    else:
        logging.error(f"❌ {folder_name} directory not found in {CURRENT_DIR} or {PARENT_DIR}")
        return local_path  # fallback

TEMPLATE_DIR = resolve_path("templates")
STATIC_DIR = resolve_path("static")

# ------------------------------------------------------------------------------
# 2. CORE IMPORTS (Safe)
# ------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("app.main")

from app.core.config import settings
from app.core.db import get_engine, init_models, Base

SCHEMA_VERSION = "unknown"
try:
    from app.core.models import SCHEMA_VERSION as ImportedSchemaVersion
    SCHEMA_VERSION = ImportedSchemaVersion
except Exception as e:
    logger.error("⚠️ Failed to load SCHEMA_VERSION", exc_info=True)

auth = companies = dashboard = reviews = exports = google_check = None
try:
    from app.routes import auth, companies, dashboard, reviews, exports, google_check
    logger.info("✅ Routers imported")
except Exception as e:
    logger.error("❌ Router import failed", exc_info=True)

# ------------------------------------------------------------------------------
# 3. SETTINGS & AUTH
# ------------------------------------------------------------------------------
ADMIN_EMAIL = "roy.jamshaid@gmail.com"
ADMIN_PASSWORD = "Jamshaid,1981"
resend.api_key = os.getenv("RESEND_API_KEY", "re_D8MWpa1c_44ph6mZDfDoCXmEkeoYtPQqC")

MAGIC_TOKENS: Dict[str, Dict[str, Any]] = {}

# ------------------------------------------------------------------------------
# 4. LIFESPAN
# ------------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 Starting Review Intel AI - Schema Version: {SCHEMA_VERSION}")
    try:
        await init_models()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error("❌ Database init failed", exc_info=True)
        raise

    app.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
    yield
    await app.state.http_client.aclose()

# ------------------------------------------------------------------------------
# 5. FASTAPI + TEMPLATES (Improved Jinja setup)
# ------------------------------------------------------------------------------
from fastapi import FastAPI, Request, Depends, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

app = FastAPI(title="Review Intel AI", version=SCHEMA_VERSION, lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Explicit template directory
templates = Jinja2Templates(directory=TEMPLATE_DIR)
logger.info(f"✅ Jinja2Templates initialized with directory: {TEMPLATE_DIR}")

def get_current_user(request: Request) -> Optional[dict]:
    return request.session.get("user")

# ------------------------------------------------------------------------------
# 6. ROUTES (with safe template rendering)
# ------------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "schema_version": SCHEMA_VERSION}

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user: Optional[dict] = Depends(get_current_user)):
    return RedirectResponse(url="/dashboard" if user else "/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None, message: Optional[str] = None):
    try:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": error,
            "message": message
        })
    except Exception as e:
        logger.error("❌ Failed to render login.html", exc_info=True)
        raise

@app.post("/login")
async def handle_login(request: Request, email: str = Form(...), password: str = Form(None)):
    # ... (your existing login logic remains unchanged) ...

    # In the magic link success part, keep the same TemplateResponse
    try:
        return templates.TemplateResponse("login.html", {"request": request, "message": "✅ Magic link sent! Please check your email inbox."})
    except Exception as e:
        logger.error("❌ Failed to render login.html after mail", exc_info=True)
        raise

# (Keep your /verify, /dashboard, /logout exactly as before, just wrap TemplateResponse in try/except if you want extra safety)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    try:
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "user": user,
            "google_api_key": getattr(settings, "GOOGLE_API_KEY", "")
        })
    except Exception as e:
        logger.error("❌ Failed to render dashboard.html", exc_info=True)
        raise

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

# Router registration (safe) - keep as in previous version
for name, router_module in [("auth", auth), ("companies", companies), ("dashboard", dashboard),
                            ("reviews", reviews), ("exports", exports), ("google_check", google_check)]:
    if router_module and hasattr(router_module, "router"):
        try:
            app.include_router(router_module.router)
            logger.info(f"✅ Included router: {name}")
        except Exception as e:
            logger.error(f"❌ Failed to include router '{name}'", exc_info=True)

# ------------------------------------------------------------------------------
# 8. STARTUP
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
