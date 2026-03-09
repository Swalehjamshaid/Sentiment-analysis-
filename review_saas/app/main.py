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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.main")

# ────────────────────────────────────────────────────────────────
# ASYNC OUTSCRAPER CLIENT (Matches ReviewSaaS Requirements)
# ────────────────────────────────────────────────────────────────
class OutscraperClient:
    """
    Handles connection to Outscraper Google Reviews API.
    Uses AsyncClient to prevent blocking the FastAPI event loop.
    """
    BASE_URL = "https://api.app.outscraper.com/google-reviews"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))

    async def get_reviews(self, place_id: str, limit: int, offset: int = 0) -> Dict[str, Any]:
        try:
            params = {
                "query": place_id,
                "limit": limit,
                "offset": offset,
                "async": "false", 
            }
            headers = {"X-API-KEY": self.api_key}
            
            logger.info(f"📡 Requesting Outscraper for Place ID: {place_id}")
            response = await self.client.get(self.BASE_URL, params=params, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"❌ API Error {response.status_code}: {response.text}")
                return {"reviews": []}

            data = response.json()
            # Navigate Outscraper's nested response structure
            if isinstance(data, list) and len(data) > 0:
                reviews = data[0].get("reviews_data", [])
                logger.info(f"✅ Received {len(reviews)} reviews.")
                return {"reviews": reviews}
            
            return {"reviews": []}
        except Exception as e:
            logger.error(f"🚨 Outscraper Client Error: {e}", exc_info=True)
            return {"reviews": []}

    async def close(self):
        await self.client.aclose()

class DummyReviewsClient:
    """Fallback client to prevent crashes if API Key is missing."""
    async def get_reviews(self, *args, **kwargs):
        logger.warning("⚠️ Dummy Client Active: No data will be fetched.")
        return {"reviews": []}
    async def close(self):
        pass

# ────────────────────────────────────────────────────────────────
# LIFESPAN & SCHEMA GUARD (Handles SCHEMA_VERSION)
# ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Database Initialization & Schema Version Check
    try:
        engine: AsyncEngine = get_engine()
        async with engine.begin() as conn:
            # Create config table if it doesn't exist to store version
            await conn.execute(text("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)"))
            
            # Check current version
            result = await conn.execute(text("SELECT value FROM config WHERE key='schema_version'"))
            row = result.first()
            db_version = row[0] if row else None

            # Compare against the SCHEMA_VERSION in models
            if db_version != str(SCHEMA_VERSION):
                logger.warning(f"🔄 Schema Mismatch: {db_version} -> {SCHEMA_VERSION}. Rebuilding Tables.")
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
                # Update version in DB
                await conn.execute(
                    text("INSERT INTO config (key, value) VALUES ('schema_version', :v) "
                         "ON CONFLICT (key) DO UPDATE SET value = :v"),
                    {"v": str(SCHEMA_VERSION)}
                )
            else:
                # Normal startup: ensure tables exist
                await conn.run_sync(Base.metadata.create_all)
                logger.info(f"✅ Database Schema is up to date (v{SCHEMA_VERSION}).")
    except Exception as e:
        logger.error(f"❌ DB Startup Error: {e}")

    # 2. Outscraper Client Initialization
    api_key = os.getenv("OUTSCRAPER_API_KEY") or os.getenv("OUTSCRAPER_KEY")
    if api_key and len(api_key) > 5:
        app.state.google_reviews_client = OutscraperClient(api_key=api_key)
        app.state.api_status = "Connected"
    else:
        app.state.google_reviews_client = DummyReviewsClient()
        app.state.api_status = "Disconnected (Key Missing)"

    yield
    # 3. Cleanup on shutdown
    await app.state.google_reviews_client.close()

# ────────────────────────────────────────────────────────────────
# APP CORE & MIDDLEWARE
# ────────────────────────────────────────────────────────────────
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# CORS and Session Middleware
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"]
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static Files and Templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# ────────────────────────────────────────────────────────────────
# ROUTES & DIAGNOSTICS
# ────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request, "settings": settings})

@app.get("/health")
async def health(request: Request):
    return {
        "status": "ok",
        "api_client": getattr(request.app.state, "api_status", "unknown"),
        "database": "connected",
        "schema_version": SCHEMA_VERSION
    }

@app.get("/api/diagnostics/db-check")
async def db_diagnostic_check(company_id: int):
    """
    Directly query the DB to see if data exists for a specific company.
    Useful for debugging why the dashboard looks empty.
    """
    async with get_session() as session:
        # Check Total Count
        count_stmt = select(func.count(Review.id)).where(Review.company_id == company_id)
        total_reviews = (await session.execute(count_stmt)).scalar() or 0
        
        # Check Date Range
        range_stmt = select(
            func.min(Review.google_review_time), 
            func.max(Review.google_review_time)
        ).where(Review.company_id == company_id)
        dates = (await session.execute(range_stmt)).first()
        
        return {
            "company_id": company_id,
            "reviews_in_db": total_reviews,
            "earliest_date": str(dates[0]) if dates[0] else "N/A",
            "latest_date": str(dates[1]) if dates[1] else "N/A",
            "api_status": app.state.api_status
        }

# Include App Routers
app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)
