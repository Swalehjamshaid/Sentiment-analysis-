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
from app.core.db import get_engine
from app.core.models import Base
# CRITICAL: Import models specifically to ensure they are registered with Base.metadata
from app.core.models import User, Company, Review 

from app.routes import auth as auth_routes
from app.routes import companies as companies_routes
from app.routes import dashboard as dashboard_routes
from app.routes import reviews as reviews_routes
from app.routes import exports as exports_routes

# Import Google API checker
from app.core.google_check import verify_google_apis

# Standard logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle manager for startup and shutdown tasks.
    Ensures database synchronization happens before the app starts.
    """
    # 1. Database Schema Synchronization
    try:
        engine: AsyncEngine = get_engine()
        async with engine.begin() as conn:
            # Create all tables defined in models.py if they don't exist
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✓ Database migration: Tables verified/created.")
    except Exception as e:
        logger.error(f"❌ Database migration failed: {e}")

    # 2. External API Verification
    try:
        verify_google_apis()
    except Exception as e:
        logger.error(f"⚠️ Google API check failed at startup: {e}")
    
    yield

app = FastAPI(
    title=settings.APP_NAME, 
    debug=settings.DEBUG,
    lifespan=lifespan
)

# Middlewares - Identical to your existing configuration
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

@app.get('/health')
async def health():
    return {"status": "ok"}
