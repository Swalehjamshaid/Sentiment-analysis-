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

# Routers
from app.routes import auth as auth_routes
from app.routes import companies as companies_routes
from app.routes import dashboard as dashboard_routes
from app.routes import reviews as reviews_routes
from app.routes import exports as exports_routes

import httpx
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# REAL OUTSCRAPER / GOOGLE REVIEWS CLIENT
# ────────────────────────────────────────────────────────────────
class OutscraperClient:
    """Real external client calling Outscraper / Google API"""

    BASE_URL = "https://api.app.outscraper.com/google-reviews"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.http = httpx.Client(timeout=30)

    def get_reviews(self, place_id: str, limit: int, offset: int) -> Dict[str, List[Dict[str, Any]]]:
        try:
            params = {
                "query": place_id,
                "amount": limit,
                "offset": offset,
            }

            headers = {
                "X-API-KEY": self.api_key
            }

            response = self.http.get(self.BASE_URL, params=params, headers=headers)
            response.raise_for_status()

            data = response.json()

            if isinstance(data, list) and len(data) > 0:
                reviews = data[0].get("data", {}).get("reviews_data", [])
                return {"reviews": reviews}

            return {"reviews": []}

        except Exception as e:
            logger.error("Outscraper API error: %s", e, exc_info=True)
            return {"reviews": []}


# ────────────────────────────────────────────────────────────────
# FALLBACK CLIENT (SAFE)
# ────────────────────────────────────────────────────────────────
class DummyReviewsClient:
    """Fallback stub — returns no reviews."""
    def get_reviews(self, place_id: str, limit: int, offset: int):
        logger.warning("[DummyReviewsClient] returning empty list for place_id=%s", place_id)
        return {"reviews": []}


# ────────────────────────────────────────────────────────────────
# LIFESPAN — DB INIT + API CLIENT ATTACHMENT
# ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        engine: AsyncEngine = get_engine()
        logger.info("Starting application...")

        async with engine.begin() as conn:
            # Check current schema version
            try:
                result = await conn.execute(
                    text("SELECT value FROM config WHERE key='schema_version'")
                )
                row = result.first()
                db_version = row[0] if row else None
            except Exception:
                db_version = None

            # Schema changed → full rebuild
            if db_version != SCHEMA_VERSION:
                logger.warning(
                    f"Schema change detected (DB={db_version}, CODE={SCHEMA_VERSION})"
                )
                logger.warning("Dropping ALL tables...")
                await conn.run_sync(Base.metadata.drop_all)

                logger.info("Creating NEW tables...")
                await conn.run_sync(Base.metadata.create_all)

                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS config (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """))

                await conn.execute(text("""
                    INSERT INTO config (key, value)
                    VALUES ('schema_version', :v)
                    ON CONFLICT(key) DO UPDATE SET value=:v
                """), {"v": SCHEMA_VERSION})

                logger.info("Database recreated successfully")

            else:
                logger.info("Database schema already up to date")
                await conn.run_sync(Base.metadata.create_all)

        # ───────────────────────────────────────────────
        # Attach REAL Outscraper / Google client
        # ───────────────────────────────────────────────
        # FIX: Check multiple possible variable names from settings and env
        api_key = (
            getattr(settings, "OUTSCRAPER_API_KEY", None) or 
            getattr(settings, "OUTSCAPTER_KEY", None) or 
            os.getenv("OUTSCRAPER_API_KEY") or 
            os.getenv("OUTSCAPTER_KEY") or 
            os.getenv("GOOGLE_REVIEWS_API_KEY")
        )

        if api_key and "PASTE" not in api_key:
            logger.info("✅ Valid API Key found. Initializing OutscraperClient...")
            app.state.google_reviews_client = OutscraperClient(api_key=api_key)
        else:
            logger.warning("⚠ No valid external review API key found. Using DummyReviewsClient.")
            app.state.google_reviews_client = DummyReviewsClient()

    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)

    yield

    logger.info("Application shutdown complete")


# ────────────────────────────────────────────────────────────────
# FASTAPI APP INIT
# ────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
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
    secret_key=settings.SECRET_KEY,
    session_cookie=settings.SESSION_COOKIE_NAME,
    same_site=settings.SESSION_COOKIE_SAMESITE,
    https_only=settings.SESSION_COOKIE_SECURE,
)


# Static & Templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# Landing Page
@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse(
        "landing.html",
        {
            "request": request,
            "title": settings.APP_NAME,
            "settings": settings,
        }
    )


# Routers
app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)


# Health Check
@app.get("/health")
async def health():
    return {"status": "ok"}
