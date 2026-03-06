# File: /app/main.py
from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy import text
from app.core.config import settings
from app.core.db import get_engine, reset_database
from app.core.models import Base, SCHEMA_VERSION  # SCHEMA_VERSION check
from app.core.models import User, Company, Review, AuditLog  # register all models
from app.routes import auth as auth_routes
from app.routes import companies as companies_routes
from app.routes import dashboard as dashboard_routes
from app.routes import reviews as reviews_routes
from app.routes import exports as exports_routes

# Import Google API check
try:
    from app.core.google_check import router as google_router
    from app.core.google_check import check_google  # async function
except ModuleNotFoundError:
    logging.warning("⚠️ Google check router not found. /api/check-google unavailable.")
    google_router = None
    async def check_google():
        logging.warning("⚠️ Google API check skipped (placeholder).")
        return {"status": "skipped"}

# Standard logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle manager: startup + shutdown.
    Drops old tables and recreates all tables whenever SCHEMA_VERSION changes or models.py updates.
    """
    try:
        engine: AsyncEngine = get_engine()
        is_dev_mode = settings.DEBUG or os.getenv("ENV", "").lower() in ("development", "dev")
        logger.info(f"Startup environment → DEBUG={settings.DEBUG}, ENV={os.getenv('ENV')}, is_dev_mode={is_dev_mode}")

        async with engine.begin() as conn:
            # Get current schema version from database
            try:
                result = await conn.execute(text("SELECT value FROM config WHERE key='schema_version'"))
                row = result.first()
                db_version = row[0] if row else None
            except Exception:
                db_version = None

            # If schema version mismatch OR forced dev reset → drop all tables
            if db_version != SCHEMA_VERSION or is_dev_mode:
                logger.warning(
                    f"Schema version mismatch or dev reset! DB: {db_version or 'missing'}, Code: {SCHEMA_VERSION} → Resetting database..."
                )

                # Drop all existing tables
                logger.info("🔥 Dropping all existing tables...")
                await conn.run_sync(Base.metadata.drop_all)

                # Recreate all tables from models.py
                logger.info("✨ Creating all tables fresh...")
                await conn.run_sync(Base.metadata.create_all)

                # Ensure config table exists and update SCHEMA_VERSION
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS config (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """))
                await conn.execute(text("""
                    INSERT INTO config (key, value)
                    VALUES ('schema_version', :ver)
                    ON CONFLICT(key) DO UPDATE SET value = :ver
                """), {"ver": SCHEMA_VERSION})

                logger.info(f"✅ Database reset complete. Schema version set to {SCHEMA_VERSION}")
            else:
                # Production: create missing tables only, preserving existing data
                logger.info("Production mode → Verified existing tables, creating missing ones if needed...")
                await conn.run_sync(Base.metadata.create_all)
                logger.info("✓ Database migration complete: tables verified/created.")

    except Exception as e:
        logger.error(f"❌ Database migration/reset failed: {e}", exc_info=True)

    # Google API check
    try:
        result = await check_google()
        logger.info(f"✓ Google API check passed: {result}")
    except Exception as e:
        logger.error(f"⚠️ Google API check failed: {e}")

    yield
    logger.info("⚡ Application shutdown complete.")

# Initialize FastAPI
app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*']
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie=settings.SESSION_COOKIE_NAME,
    same_site=settings.SESSION_COOKIE_SAMESITE,
    https_only=settings.SESSION_COOKIE_SECURE
)

# Static files & templates
app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')

# Landing page
@app.get('/', response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse('landing.html', {
        "request": request,
        "title": settings.APP_NAME,
        "settings": settings
    })

# Include routers
app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)

# Google router
if google_router:
    app.include_router(google_router, prefix="/api")

# Health check
@app.get('/health')
async def health():
    return {"status": "ok"}
