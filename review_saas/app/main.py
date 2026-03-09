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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
# COMPREHENSIVE OUTSCRAPER CLIENT
# ────────────────────────────────────────────────────────────────
class OutscraperClient:
    """
    Handles the actual connection to Outscraper. 
    Matches the specific nested JSON structure returned by their Google Reviews endpoint.
    """
    BASE_URL = "https://api.app.outscraper.com/google-reviews"

    def __init__(self, api_key: str):
        self.api_key = api_key
        # Use an AsyncClient for better performance with FastAPI
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))

    async def get_reviews(self, place_id: str, limit: int, offset: int = 0) -> Dict[str, Any]:
        """
        Fetches reviews. Outscraper returns a list of results (one per query).
        We extract 'reviews_data' from the first result.
        """
        try:
            params = {
                "query": place_id,
                "limit": limit,
                "offset": offset,
                "async": "false", # Ensure synchronous response for the ingestion task
            }
            headers = {"X-API-KEY": self.api_key}
            
            logger.info(f"📡 Requesting Outscraper for Place ID: {place_id}")
            response = await self.client.get(self.BASE_URL, params=params, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"❌ Outscraper returned error {response.status_code}: {response.text}")
                return {"reviews": []}

            data = response.json()

            # Outscraper's standard response is a list containing a result object
            if isinstance(data, list) and len(data) > 0:
                # The reviews are located inside data[0] -> reviews_data
                reviews = data[0].get("reviews_data", [])
                logger.info(f"✅ Successfully fetched {len(reviews)} reviews from Outscraper.")
                return {"reviews": reviews}
            
            return {"reviews": []}
        except Exception as e:
            logger.error(f"🚨 Outscraper API Client error: {e}", exc_info=True)
            return {"reviews": []}

    async def close(self):
        await self.client.aclose()

class DummyReviewsClient:
    """Fallback client when no API Key is found."""
    async def get_reviews(self, *args, **kwargs):
        logger.warning("⚠️ [DummyReviewsClient] ACTIVE - Review sync will yield no results.")
        return {"reviews": []}
    async def close(self):
        pass

# ────────────────────────────────────────────────────────────────
# LIFESPAN & ENGINE SETUP
# ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Database Initialization
    try:
        engine: AsyncEngine = get_engine()
        async with engine.begin() as conn:
            # Check/Create config table for schema versioning
            await conn.execute(text("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)"))
            result = await conn.execute(text("SELECT value FROM config WHERE key='schema_version'"))
            row = result.first()
            db_version = row[0] if row else None

            if db_version != str(SCHEMA_VERSION):
                logger.warning(f"🔄 Schema Mismatch ({db_version} vs {SCHEMA_VERSION}). Rebuilding...")
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
                await conn.execute(
                    text("INSERT INTO config (key, value) VALUES ('schema_version', :v) ON CONFLICT (key) DO UPDATE SET value = :v"),
                    {"v": str(SCHEMA_VERSION)}
                )
            else:
                await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        logger.error(f"❌ Database startup failed: {e}")

    # 2. API Client Setup
    # Check multiple possible env var names for reliability on Railway/Local
    api_key = os.getenv("OUTSCRAPER_API_KEY") or os.getenv("OUTSCRAPER_KEY")
    
    if api_key and len(api_key) > 5:
        app.state.google_reviews_client = OutscraperClient(api_key=api_key)
        app.state.api_status = "Connected"
        logger.info("🚀 Outscraper API Client initialized.")
    else:
        app.state.google_reviews_client = DummyReviewsClient()
        app.state.api_status = "Disconnected (API Key Missing)"
        logger.error("🛑 No Outscraper API Key found. Reviews will NOT sync.")

    yield
    # 3. Shutdown
    await app.state.google_reviews_client.close()

# ────────────────────────────────────────────────────────────────
# APP DEFINITION
# ────────────────────────────────────────────────────────────────
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# Middleware
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"]
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static & Templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request, "settings": settings})

# Include all Routers
app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)

@app.get("/health")
async def health(request: Request):
    return {
        "status": "ok",
        "api_client": getattr(request.app.state, "api_status", "unknown"),
        "database": "connected",
        "schema_version": SCHEMA_VERSION
    }
