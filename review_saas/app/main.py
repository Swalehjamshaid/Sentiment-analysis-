# filename: app/main.py

# ============================================================
# SQLAlchemy Deprecation Warning Suppression (REQUIRED)
# ============================================================
import warnings
from sqlalchemy.exc import SADeprecationWarning

warnings.filterwarnings("ignore", category=SADeprecationWarning)

# ============================================================
# Standard Library Imports
# ============================================================
import sys
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional, Tuple

# ============================================================
# Path Fix for Docker / Gunicorn
# ============================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

# ============================================================
# FastAPI & Framework Imports
# ============================================================
from fastapi import FastAPI, Request, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

# ============================================================
# SQLAlchemy Imports
# ============================================================
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ============================================================
# Project Imports
# ============================================================
from app.core.config import settings
from app.core.db import init_models, get_session, SessionLocal, engine
from app.core import models
from app.core.models import User, SCHEMA_VERSION, Config
from app.core.security import verify_password

# Routers
from app.routes import auth, companies, dashboard, reviews, exports, google_check

# ============================================================
# Logging Configuration
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

# ============================================================
# Schema Version Helpers (FIXED — NO SYNTAX ERRORS)
# ============================================================
async def _get_stored_schema_version(
    session: AsyncSession,
) -> Optional[str]:
    result = await session.execute(
        select(Config).where(Config.key == "SCHEMA_VERSION")
    )
    row = result.scalar_one_or_none()
    return row.value if row else None


async def _set_stored_schema_version(
    session: AsyncSession,
    new_value: str,
) -> None:
    result = await session.execute(
        select(Config).where(Config.key == "SCHEMA_VERSION")
    )
    row = result.scalar_one_or_none()
    if row:
        row.value = new_value
    else:
        session.add(Config(key="SCHEMA_VERSION", value=new_value))
    await session.commit()


async def check_schema_version_change() -> Tuple[bool, Optional[str], str]:
    async with SessionLocal() as session:
        old_version = await _get_stored_schema_version(session)
        new_version = str(SCHEMA_VERSION)

        if old_version is None:
            await _set_stored_schema_version(session, new_version)
            logger.info(f"📦 Schema initialized: {new_version}")
            return False, None, new_version

        if old_version != new_version:
            logger.warning(f"🧩 Schema changed: {old_version} → {new_version}")
            return True, old_version, new_version

        return False, old_version, new_version

# ============================================================
# SAFE SCHEMA APPLICATION (NO DROP, NO DATA LOSS)
# ============================================================
async def apply_schema_updates():
    """
    - Creates new tables
    - Adds new columns (DB dependent)
    - NEVER drops existing data
    """
    async with engine.begin() as conn:
        def _safe_create(sync_conn):
            models.Base.metadata.create_all(bind=sync_conn)
        await conn.run_sync(_safe_create)
    logger.info("✅ Schema applied safely")

# ============================================================
# Application Lifespan
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Review Intel AI")
    try:
        await init_models()

        changed, _, new_version = await check_schema_version_change()
        if changed:
            await apply_schema_updates()
            async with SessionLocal() as session:
                await _set_stored_schema_version(session, new_version)

        app.state.schema_version = new_version
        logger.info(f"✅ Startup complete | Schema {new_version}")

    except Exception:
        logger.exception("❌ Startup failed")
        raise

    yield

# ============================================================
# FastAPI App Initialization
# ============================================================
app = FastAPI(
    title=getattr(settings, "APP_NAME", "Review SaaS AI"),
    lifespan=lifespan,
)

# ============================================================
# Middleware
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
)

# ============================================================
# Static & Templates
# ============================================================
if os.path.exists(os.path.join(CURRENT_DIR, "static")):
    app.mount(
        "/static",
        StaticFiles(directory=os.path.join(CURRENT_DIR, "static")),
        name="static",
    )

templates = Jinja2Templates(
    directory=os.path.join(CURRENT_DIR, "templates")
)

# ============================================================
# Views (HTML)
# ============================================================
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return (
        RedirectResponse("/dashboard")
        if request.session.get("user")
        else RedirectResponse("/login")
    )


@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(User).where(User.email == email.strip().lower())
    )
    user = result.scalars().first()

    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid credentials"},
        )

    request.session["user"] = {
        "id": user.id,
        "email": user.email,
        "name": user.name,
    }

    return RedirectResponse("/dashboard", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "schema_version": getattr(app.state, "schema_version", ""),
        },
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# ============================================================
# Router Registration
# ============================================================
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])
app.include_router(exports.router, prefix="/api", tags=["exports"])
app.include_router(google_check.router, prefix="/api", tags=["google_check"])

# ============================================================
# Local Run
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
    )
