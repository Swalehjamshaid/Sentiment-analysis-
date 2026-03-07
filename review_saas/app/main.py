# File: /app/main.py

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings
from app.core.db import get_engine
from app.core.models import Base, SCHEMA_VERSION

# Import routers (no attribute changes)
from app.routes import auth as auth_routes
from app.routes import companies as companies_routes
from app.routes import dashboard as dashboard_routes
from app.routes import reviews as reviews_routes
from app.routes import exports as exports_routes

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --------------------------------------------------
# Lifespan manager (database initialization)
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):

    try:

        engine: AsyncEngine = get_engine()

        logger.info("Starting application...")

        async with engine.begin() as conn:

            logger.info("Creating database tables if missing")

            # This WILL NOT delete existing tables
            await conn.run_sync(Base.metadata.create_all)

            logger.info("Database tables verified")

    except Exception as e:

        logger.error(f"Database initialization failed: {e}", exc_info=True)

    yield

    logger.info("Application shutdown complete")


# --------------------------------------------------
# FastAPI app (THIS FIXES YOUR ERROR)
# --------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan
)


# --------------------------------------------------
# Middleware
# --------------------------------------------------

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
    session_cookie=settings.SESSION_COOKIE_NAME,
    same_site=settings.SESSION_COOKIE_SAMESITE,
    https_only=settings.SESSION_COOKIE_SECURE,
)


# --------------------------------------------------
# Static + Templates
# --------------------------------------------------

app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")


# --------------------------------------------------
# Landing Page
# --------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):

    return templates.TemplateResponse(
        "landing.html",
        {
            "request": request,
            "title": settings.APP_NAME,
            "settings": settings
        }
    )


# --------------------------------------------------
# Routers (no attributes removed)
# --------------------------------------------------

app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)


# --------------------------------------------------
# Health check
# --------------------------------------------------

@app.get("/health")
async def health():

    return {"status": "ok"}
