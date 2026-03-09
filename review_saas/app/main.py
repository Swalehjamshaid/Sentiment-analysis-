# filename: app/main.py
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy import text, select, func

from app.core.config import settings
from app.core.db import get_engine, get_session
from app.core.models import Base, SCHEMA_VERSION, Company, Review

# Routers
from app.routes import auth as auth_routes
from app.routes import companies as companies_routes
from app.routes import dashboard as dashboard_routes
from app.routes import reviews as reviews_routes
from app.routes import exports as exports_routes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

# ────────────────────────────────────────────────────────────────
# ROBUST OUTSCRAPER CLIENT (Ingestion Fix)
# ────────────────────────────────────────────────────────────────
class OutscraperClient:
    """
    Handles connection to Outscraper Google Reviews API.
    Fix: Correctly parses the nested 'reviews_data' from list response.
    """
    BASE_URL = "https://api.app.outscraper.com/google-reviews"

    def __init__(self, api_key: str):
        self.api_key = api_key
        # High timeout because scraping can be slow
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))

    async def get_reviews(self, place_id: str, limit: int = 200, offset: int = 0) -> Dict[str, Any]:
        try:
            params = {
                "query": place_id,
                "limit": limit,
                "offset": offset,
                "async": "false",  # Synchronous for simpler handling
            }
            headers = {"X-API-KEY": self.api_key}

            logger.info(f"📡 Requesting Outscraper reviews for Place ID: {place_id}")
            response = await self.client.get(self.BASE_URL, params=params, headers=headers)

            if response.status_code != 200:
                logger.error(f"❌ Outscraper API Error {response.status_code}: {response.text}")
                return {"reviews": []}

            data = response.json()

            # CRITICAL FIX: Outscraper returns list → first item → reviews_data
            if isinstance(data, list) and len(data) > 0:
                query_result = data[0]
                reviews = query_result.get("reviews_data", [])

                if not reviews and query_result.get("error"):
                    logger.warning(f"⚠️ Outscraper error: {query_result['error']}")

                logger.info(f"✅ Fetched {len(reviews)} reviews for {place_id}")
                return {"reviews": reviews}

            logger.warning("⚠️ Outscraper returned unexpected format (not a list or empty).")
            return {"reviews": []}

        except Exception as e:
            logger.error(f"🚨 Outscraper Client Failure: {e}", exc_info=True)
            return {"reviews": []}

    async def close(self):
        await self.client.aclose()


class DummyReviewsClient:
    """Fallback when API key is missing — prevents crash but logs warning."""
    async def get_reviews(self, *args, **kwargs):
        logger.warning("⚠️ DUMMY MODE: No real reviews will be fetched.")
        return {"reviews": []}

    async def close(self):
        pass


# ────────────────────────────────────────────────────────────────
# LIFESPAN (Startup / Shutdown)
# ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 1. Database Setup & Auto-Migration ───────────────────────
    try:
        engine: AsyncEngine = get_engine()
        async with engine.begin() as conn:
            # Ensure config table exists
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """))

            # Check schema version
            result = await conn.execute(text("SELECT value FROM config WHERE key='schema_version'"))
            row = result.first()
            db_version = row[0] if row else None

            if db_version != str(SCHEMA_VERSION):
                logger.warning(f"🔄 Schema mismatch: DB v{db_version} → v{SCHEMA_VERSION}. Rebuilding...")
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)

                # Update version
                await conn.execute(
                    text("""
                        INSERT INTO config (key, value) 
                        VALUES ('schema_version', :v)
                        ON CONFLICT (key) DO UPDATE SET value = :v
                    """),
                    {"v": str(SCHEMA_VERSION)}
                )
                logger.info(f"✅ Schema rebuilt to v{SCHEMA_VERSION}")
            else:
                await conn.run_sync(Base.metadata.create_all)
                logger.info(f"✅ Schema v{SCHEMA_VERSION} verified.")
    except Exception as e:
        logger.error(f"❌ Database startup failed: {e}", exc_info=True)

    # ── 2. Outscraper Client Initialization ──────────────────────
    api_key = os.getenv("OUTSCRAPER_API_KEY") or getattr(settings, "OUTSCRAPER_API_KEY", None)

    if api_key and len(api_key) > 10:
        app.state.google_reviews_client = OutscraperClient(api_key=api_key)
        app.state.api_status = "Connected"
        logger.info("🚀 Outscraper Client: CONNECTED")
    else:
        app.state.google_reviews_client = DummyReviewsClient()
        app.state.api_status = "Disconnected (API Key Missing)"
        logger.error("🛑 OUTSCRAPER_API_KEY missing. Sync will NOT fetch real reviews.")

    yield  # App runs here

    # ── 3. Shutdown ───────────────────────────────────────────────
    if hasattr(app.state, "google_reviews_client"):
        await app.state.google_reviews_client.close()
        logger.info("Outscraper client closed.")


# ────────────────────────────────────────────────────────────────
# FASTAPI APP
# ────────────────────────────────────────────────────────────────
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static files & templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ────────────────────────────────────────────────────────────────
# DIAGNOSTICS & HEALTH ROUTES
# ────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request, "settings": settings})


@app.get("/health")
async def health():
    """Health check for Railway / monitoring."""
    return {
        "status": "ok",
        "api_client": getattr(app.state, "api_status", "unknown"),
        "database": "connected",
        "schema_version": SCHEMA_VERSION
    }


@app.get("/api/diagnostics/db-check")
async def db_diagnostic_check(company_id: int):
    """
    Debug endpoint: Check if reviews exist for a company.
    Call this if dashboard shows 0 everywhere.
    Example: /api/diagnostics/db-check?company_id=1
    """
    async with get_session() as session:
        count_stmt = select(func.count(Review.id)).where(Review.company_id == company_id)
        count_res = await session.execute(count_stmt)
        total_reviews = count_res.scalar() or 0

        range_stmt = select(
            func.min(Review.google_review_time),
            func.max(Review.google_review_time)
        ).where(Review.company_id == company_id)
        range_res = await session.execute(range_stmt)
        dates = range_res.first()

        return {
            "company_id": company_id,
            "reviews_in_database": total_reviews,
            "earliest_review": str(dates[0]) if dates[0] else "None",
            "latest_review": str(dates[1]) if dates[1] else "None",
            "api_status": getattr(app.state, "api_status", "unknown")
        }


# ────────────────────────────────────────────────────────────────
# INCLUDE ROUTERS
# ────────────────────────────────────────────────────────────────
app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)
