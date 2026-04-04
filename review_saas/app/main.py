# filename: app/main.py
import sys
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional, Tuple

import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from fastapi import FastAPI, Request, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ------------------------------------------------------------------------------
# 0. SENTRY (Early - captures import & startup errors better)
# ------------------------------------------------------------------------------
try:
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        integrations=[
            AsyncioIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        traces_sample_rate=0.1,
        environment=os.getenv("ENVIRONMENT", "production"),
    )
    logging.info("✅ Sentry initialized")
except Exception as e:
    logging.error("❌ Failed to init Sentry", exc_info=True)

# ------------------------------------------------------------------------------
# Fix for Docker / Railway import issues
# ------------------------------------------------------------------------------
sys.path.insert(0, "/app")
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

# ------------------------------------------------------------------------------
# Core imports
# ------------------------------------------------------------------------------
from app.core.config import settings
from app.core.db import init_models, get_session, SessionLocal, engine
from app.core import models
from app.core.models import User, SCHEMA_VERSION, Config as ConfigModel

# Routers
from app.routes import auth, companies, dashboard, reviews, exports, google_check

# ------------------------------------------------------------------------------
# Dynamic Path Resolution (Critical for Railway/Docker)
# ------------------------------------------------------------------------------
def resolve_path(folder_name: str) -> str:
    """Works reliably in local dev and Docker/Railway."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)

    candidates = [
        os.path.join(current_dir, folder_name),      # app/templates
        os.path.join(parent_dir, folder_name),       # templates (if structure is flat)
        os.path.join("/app", folder_name),           # common in Railway
        os.path.join(os.getcwd(), folder_name),
    ]

    for path in candidates:
        if os.path.exists(path):
            logger.info(f"✅ Found {folder_name} at: {path}")
            return path

    logger.error(f"❌ {folder_name} directory NOT FOUND in any expected location!")
    # Fallback
    return os.path.join(current_dir, folder_name)

TEMPLATE_DIR = resolve_path("templates")
STATIC_DIR = resolve_path("static")

# ------------------------------------------------------------------------------
# Schema Helpers (unchanged)
# ------------------------------------------------------------------------------
async def _get_stored_schema_version(session: AsyncSession) -> Optional[str]:
    res = await session.execute(
        select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION")
    )
    row = res.scalar_one_or_none()
    return row.value if row else None

async def _set_stored_schema_version(session: AsyncSession, new_value: str) -> None:
    res = await session.execute(
        select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION")
    )
    row = res.scalar_one_or_none()
    if row:
        row.value = new_value
    else:
        row = ConfigModel(key="SCHEMA_VERSION", value=new_value)
        session.add(row)
    await session.commit()

async def check_schema_version_change() -> Tuple[bool, Optional[str], str]:
    async with SessionLocal() as session:
        old_version = await _get_stored_schema_version(session)
        new_version = str(SCHEMA_VERSION)
        if old_version is None:
            await _set_stored_schema_version(session, new_version)
            logger.info("📦 Initialized SCHEMA_VERSION: %s", new_version)
            return False, None, new_version
        if old_version != new_version:
            logger.warning("🧩 SCHEMA changed: %s → %s", old_version, new_version)
            return True, old_version, new_version
        logger.info("✅ SCHEMA_VERSION verified: %s", new_version)
        return False, old_version, new_version

async def reset_database_schema():
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)
        logger.warning("🧨 Dropped all tables")
        await conn.run_sync(models.Base.metadata.create_all)
        logger.info("🧱 Recreated all tables")

# ------------------------------------------------------------------------------
# Lifespan (unchanged logic)
# ------------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Application Startup Started...")
    try:
        await init_models()
        changed, old_v, new_v = await check_schema_version_change()
        if changed:
            await reset_database_schema()
            async with SessionLocal() as session:
                await _set_stored_schema_version(session, new_v)
        app.state.schema_version = new_v
        logger.info("✅ SCHEMA_VERSION verified: %s", new_v)
        logger.info("🚀 Application Startup Complete")
    except Exception as e:
        logger.error("❌ Error during startup", exc_info=True)
    yield
    logger.info("🛑 Application Shutdown Started...")

# ------------------------------------------------------------------------------
# App Init
# ------------------------------------------------------------------------------
app = FastAPI(
    title=getattr(settings, "APP_NAME", "Review SaaS AI"),
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "super-secret-key"),
)

# Static & Templates (Fixed)
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    logger.info(f"✅ Static files mounted from: {STATIC_DIR}")
else:
    logger.warning(f"⚠️ Static directory not found: {STATIC_DIR}")

templates = Jinja2Templates(directory=TEMPLATE_DIR)
logger.info(f"✅ Jinja2Templates initialized with: {TEMPLATE_DIR}")

# Auth Helper
def get_current_user(request: Request):
    return request.session.get("user")

# ------------------------------------------------------------------------------
# Views (Safe Template Rendering)
# ------------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if get_current_user(request):
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    try:
        return templates.TemplateResponse("login.html", {"request": request})
    except Exception as e:
        logger.error("❌ Failed to render login.html", exc_info=True)
        raise

@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if not user or password != user.hashed_password:
        try:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Invalid credentials"},
            )
        except Exception as e:
            logger.error("❌ Failed to render login.html with error", exc_info=True)
            raise

    request.session["user"] = {
        "id": user.id,
        "email": user.email,
        "name": user.name,
    }
    return RedirectResponse("/dashboard", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    try:
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "user": user,
                "schema_version": getattr(app.state, "schema_version", ""),
            },
        )
    except Exception as e:
        logger.error("❌ Failed to render dashboard.html", exc_info=True)
        raise

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# ------------------------------------------------------------------------------
# Routers
# ------------------------------------------------------------------------------
logger.info("🔗 Mounting all routers...")
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])
app.include_router(exports.router, prefix="/api", tags=["exports"])
app.include_router(google_check.router, prefix="/api", tags=["google_check"])
logger.info("🔗 All routers mounted correctly")

# ------------------------------------------------------------------------------
# Run (local/testing only)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
