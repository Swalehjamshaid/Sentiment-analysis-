# filename: app/main.py
from __future__ import annotations
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

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

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

app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')

@app.on_event('startup')
async def on_startup():
    engine: AsyncEngine = get_engine()
    # This block instructs SQLAlchemy to create all tables defined in models.py
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✓ Database migration: Tables verified/created.")

    # --------- Google API Verification ---------
    try:
        verify_google_apis()
    except Exception as e:
        print(f"⚠️ Google API check failed at startup: {e}")

@app.get('/', response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse('landing.html', {
        "request": request, 
        "title": settings.APP_NAME, 
        "settings": settings
    })

# Routers
app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)

@app.get('/health')
async def health():
    return {"status": "ok"}
