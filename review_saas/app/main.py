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
from sqlalchemy import text

from app.core.config import settings
from app.core.db import get_engine
from app.core.models import Base, SCHEMA_VERSION

# Import routers (no attribute changes)
from app.routes import auth as auth_routes
from app.routes import companies as companies_routes
from app.routes import dashboard as dashboard_routes
from app.routes import reviews as reviews_routes
from app.routes import exports as exports_routes

# NEW: typing + httpx for external API client (optional; stub below doesn't need httpx)
from typing import Any, Dict, List, Optional

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# (NEW) External Reviews Client Wiring
#   - The dashboard routes expect app.state.google_reviews_client
#   - It must implement: get_reviews(place_id: str, limit: int, offset: int) -> {"reviews": [...]}
#   - Replace DummyReviewsClient with your real Outscraper/Google client when ready.
# ──────────────────────────────────────────────────────────────────────────────
class DummyReviewsClient:
    """
    Minimal interface-compatible client.
    Replace this with your actual Outscraper/Google client implementation.

    Required method:
        get_reviews(place_id: str, limit: int, offset: int) -> dict
            Returns {"reviews": [ { ... } ]}
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OUTSCRAPER_API_KEY") or os.getenv("GOOGLE_REVIEWS_API_KEY")

    def get_reviews(self, place_id: str, limit: int, offset: int) -> Dict[str, List[Dict[str, Any]]]:
        # TODO: Replace stub with a real call.
        # This stub returns an empty page so your system behaves but fetches 0 rows.
        # Once you plug a real client, the date-wise ingest will populate the DB correctly.
        logger.warning("DummyReviewsClient in use: returning empty page (place_id=%s, limit=%s, offset=%s)", place_id, limit, offset)
        return {"reviews": []}


# --------------------------------------------------
# Lifespan manager (database initialization + client attach)
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):

    try:

        engine: AsyncEngine = get_engine()

        logger.info("Starting application...")

        async with engine.begin() as conn:

            # ---------------------------------------
            # Check schema version in database
            # ---------------------------------------

            try:
                result = await conn.execute(
                    text("SELECT value FROM config WHERE key='schema_version'")
                )
                row = result.first()
                db_version = row[0] if row else None
            except Exception:
                db_version = None

            # ---------------------------------------
            # If schema changed → recreate database
            # ---------------------------------------

            if db_version != SCHEMA_VERSION:

                logger.warning(
                    f"Schema change detected (DB={db_version}, CODE={SCHEMA_VERSION})"
                )

                logger.warning("Dropping ALL tables...")

                await conn.run_sync(Base.metadata.drop_all)

                logger.info("Creating NEW database tables...")

                await conn.run_sync(Base.metadata.create_all)

                # ensure config table exists
                await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """))

                await conn.execute(text("""
                INSERT INTO config (key,value)
                VALUES ('schema_version', :ver)
                ON CONFLICT(key)
                DO UPDATE SET value=:ver
                """), {"ver": SCHEMA_VERSION})

                logger.info("Database recreated successfully")

            else:

                logger.info("Database schema already up to date")

                # Only create missing tables
                await conn.run_sync(Base.metadata.create_all)

        # ─────────────────────────────────────────
        # (NEW) Attach external reviews client
        # ─────────────────────────────────────────
        # Prefer a real client if you have one; fall back to DummyReviewsClient
        # Env hints (set any of these in Railway/Env):
        #   OUTSCRAPER_API_KEY, GOOGLE_REVIEWS_API_KEY
        # If you have a concrete class, import and instantiate here:
        #
        # from app.services.google_api_client import GoogleReviewsClient
        # app.state.google_reviews_client = GoogleReviewsClient(api_key=os.getenv("OUTSCRAPER_API_KEY"))
        #
        # For now we attach a dummy (returns empty pages); replace it with real client to fetch data.
        if not hasattr(app.state, "google_reviews_client") or app.state.google_reviews_client is None:
            app.state.google_reviews_client = DummyReviewsClient()
            logger.info("google_reviews_client attached to app.state (class=%s)", app.state.google_reviews_client.__class__.__name__)

    except Exception as e:

        logger.error(f"Database initialization failed: {e}", exc_info=True)

    yield

    logger.info("Application shutdown complete")


# --------------------------------------------------
# FastAPI app
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
