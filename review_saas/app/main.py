# File: /app/main.py
from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncEngine
from app.core.config import settings
from app.core.db import get_engine, reset_database   # ← ADDED: import reset_database
from app.core.models import Base
from app.core.models import User, Company, Review # CRITICAL: register models
from app.routes import auth as auth_routes
from app.routes import companies as companies_routes
from app.routes import dashboard as dashboard_routes
from app.routes import reviews as reviews_routes
from app.routes import exports as exports_routes
# Import the Google API check endpoint
try:
    from app.core.google_check import router as google_router
    from app.core.google_check import check_google # the async function
except ModuleNotFoundError:
    logging.warning("⚠️ Google check router not found. /api/check-google will be unavailable.")
    google_router = None
    async def check_google():
        logging.warning("⚠️ Google API check skipped (placeholder).")
        return {"status": "skipped"}
# Standard logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle manager for startup tasks.
    Ensures database synchronization and Google API check happen before the app starts.
    """
    # 1. Database Schema Synchronization + Reset in development mode
    try:
        engine: AsyncEngine = get_engine()
        
        # ── ADDED: Full reset (drop + recreate) only in development mode ──
        if settings.DEBUG:
            logger.warning("⚠️ DEVELOPMENT MODE: Resetting database (dropping all tables and recreating)...")
            await reset_database()
            logger.info("✅ Database has been fully reset and tables recreated from models.")
        else:
            # Normal behavior in production: just ensure tables exist
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("✓ Database migration: Tables verified/created.")
            
    except Exception as e:
        logger.error(f"❌ Database migration / reset failed: {e}")
    
    # 2. Active Google API check at startup
    try:
        result = await check_google()
        logger.info(f"✓ Google API check passed at startup: {result}")
    except Exception as e:
        logger.error(f"⚠️ Google API check failed at startup: {e}")
   
    yield
    # Place for shutdown tasks if needed
    logger.info("⚡ Application shutdown complete.")

# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan
)

# Middlewares
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

# Static files and templates
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

# Router Inclusions
app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)

# Include Google check router if available
if google_router:
    app.include_router(google_router, prefix="/api")

# Health endpoint
@app.get('/health')
async def health():
    return {"status": "ok"}
