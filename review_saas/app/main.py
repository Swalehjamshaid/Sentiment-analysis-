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
# CRITICAL: Import models here so SQLAlchemy knows they exist
from app.core import models 

from app.routes import auth as auth_routes
from app.routes import companies as companies_routes
from app.routes import dashboard as dashboard_routes
from app.routes import reviews as reviews_routes
from app.routes import exports as exports_routes

# Import Google API checker
from app.core.google_check import verify_google_apis

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown logic.
    Replaces the deprecated @app.on_event('startup') for better reliability.
    """
    # 1. Database Migration
    try:
        engine: AsyncEngine = get_engine()
        async with engine.begin() as conn:
            # Instructs SQLAlchemy to create all tables defined in models.py
            await conn.run_sync(Base.metadata.create_all)
        print("✓ Database migration: Tables verified/created.")
    except Exception as e:
        print(f"❌ Database migration failed: {e}")

    # 2. Google API Verification (Non-blocking)
    try:
        verify_google_apis()
    except Exception as e:
        print(f"⚠️ Google API check failed at startup: {e}")
    
    yield
    # Shutdown logic goes here if needed

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

# SESSION FIX: Ensuring a secret_key exists prevents 401/Session errors
app.add_middleware(
    SessionMiddleware, 
    secret_key=settings.SECRET_KEY or "development_secret_key_check_railway_vars", 
    session_cookie=settings.SESSION_COOKIE_NAME, 
    same_site=settings.SESSION_COOKIE_SAMESITE, 
    https_only=settings.SESSION_COOKIE_SECURE
)

app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')

@app.get('/', response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse('landing.html', {
        "request": request, 
        "title": settings.APP_NAME, 
        "settings": settings
    })

# Routers - All attributes and paths kept identical
app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)

@app.get('/health')
async def health():
    return {"status": "ok"}
