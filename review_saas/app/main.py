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

from fastapi import FastAPI, Request, Depends, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

# ------------------------------------------------------------------------------
# 1. MODULE & PATH RESOLUTION
# ------------------------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

def resolve_path(folder_name: str) -> str:
    local_path = os.path.join(CURRENT_DIR, folder_name)
    parent_path = os.path.join(PARENT_DIR, folder_name)
    return local_path if os.path.exists(local_path) else parent_path

TEMPLATE_DIR = resolve_path("templates")
STATIC_DIR = resolve_path("static")

# ------------------------------------------------------------------------------
# Sentry Setup (Recommended)
# ------------------------------------------------------------------------------
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
import logging as std_logging

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    integrations=[
        FastApiIntegration(),
        AsyncioIntegration(),
        LoggingIntegration(
            level=std_logging.INFO,
            event_level=std_logging.ERROR,
        ),
    ],
    traces_sample_rate=0.2,
    environment=os.getenv("ENVIRONMENT", "production"),
)

# ------------------------------------------------------------------------------
# 2. CORE INTEGRATION (DB & MODELS) - Safer import for SCHEMA_VERSION
# ------------------------------------------------------------------------------
from app.core.config import settings
from app.core.db import get_engine, init_models, Base

# Safe import of SCHEMA_VERSION with fallback
SCHEMA_VERSION = "unknown"
try:
    from app.core.models import SCHEMA_VERSION as ImportedSchemaVersion
    SCHEMA_VERSION = ImportedSchemaVersion
except Exception as e:
    logging.error(f"⚠️ Failed to import SCHEMA_VERSION from models.py: {e}", exc_info=True)

# Import Routers safely
try:
    from app.routes import auth, companies, dashboard, reviews, exports, google_check
except ImportError as e:
    logging.error(f"⚠️ Router Import Warning: {e}")
    auth = companies = dashboard = reviews = exports = google_check = None

# ------------------------------------------------------------------------------
# 3. SETTINGS & AUTH CONFIGURATION
# ------------------------------------------------------------------------------
ADMIN_EMAIL = "roy.jamshaid@gmail.com"
ADMIN_PASSWORD = "Jamshaid,1981"
resend.api_key = os.getenv("RESEND_API_KEY", "re_D8MWpa1c_44ph6mZDfDoCXmEkeoYtPQqC")

MAGIC_TOKENS: Dict[str, Dict[str, Any]] = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("app.main")

# ------------------------------------------------------------------------------
# 4. LIFESPAN (Safe + Clear error reporting)
# ------------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 Starting Review Intel AI - Schema Version: {SCHEMA_VERSION}")

    try:
        await init_models()
        logger.info("✅ Database models initialized successfully.")
    except Exception as e:
        logger.error("❌ Database initialization failed during startup", exc_info=True)
        raise RuntimeError(f"Startup failed: Database initialization error - {str(e)}") from e

    app.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))

    yield

    await app.state.http_client.aclose()
    logger.info("🛑 Application shutdown completed.")

# ------------------------------------------------------------------------------
# 5. FASTAPI APP SETUP
# ------------------------------------------------------------------------------
app = FastAPI(
    title="Review Intel AI",
    version=SCHEMA_VERSION,          # Safe fallback used here
    lifespan=lifespan
)

# Middlewares and static files (unchanged)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATE_DIR)

def get_current_user(request: Request) -> Optional[dict]:
    return request.session.get("user")

# ------------------------------------------------------------------------------
# Routes (login, verify, dashboard, etc.) - unchanged except for brevity
# ------------------------------------------------------------------------------

# ... [your existing /health, /, /login, /verify, /dashboard, /logout routes go here]

# ------------------------------------------------------------------------------
# 7. ROUTER REGISTRATION
# ------------------------------------------------------------------------------
if auth: app.include_router(auth.router)
if companies: app.include_router(companies.router)
if dashboard: app.include_router(dashboard.router)
if reviews: app.include_router(reviews.router)
if exports: app.include_router(exports.router)
if google_check: app.include_router(google_check.router)

# ------------------------------------------------------------------------------
# 8. PRODUCTION STARTUP
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
