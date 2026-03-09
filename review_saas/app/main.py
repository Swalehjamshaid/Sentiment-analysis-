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

# Configure logging to be more descriptive for debugging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

# ────────────────────────────────────────────────────────────────
# ROBUST OUTSCRAPER CLIENT (The "Ingestion Fix")
# ────────────────────────────────────────────────────────────────
class OutscraperClient:
    """
    Handles connection to Outscraper Google Reviews API.
    Fix: Correctly parses the 'reviews_data' from the nested list response.
    """
    BASE_URL = "https://api.app.outscraper.com/google-reviews"

    def __init__(self, api_key: str):
        self.api_key = api_key
        # Use a high timeout (120s) because Google scraping can take time
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))

    async def get_reviews(self, place_id: str, limit: int, offset: int = 0) -> Dict[str, Any]:
        try:
            params = {
                "query": place_id,
                "limit": limit,
                "offset": offset,
                "async": "false", # Use synchronous cloud execution for simpler logic
            }
            headers = {"X-API-KEY": self.api_key}
            
            logger.info(f"📡 Requesting Outscraper for Place ID: {place_id}")
            response = await self.client.get(self.BASE_URL, params=params, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"❌ Outscraper API Error {response.status_code}: {response.text}")
                return {"reviews": []}

            data = response.json()
            
            # CRITICAL FIX: Outscraper returns a list of query results.
            # We must drill down: data -> [0] -> reviews_data
            if isinstance(data, list) and len(data) > 0:
                # The first item in the list is the result for our query
                query_result = data[0]
                reviews = query_result.get("reviews_data", [])
                
                # If reviews_data is empty, check for error messages in the response
                if not reviews and query_result.get("error"):
                    logger.warning(f"⚠️ Outscraper reported an error: {query_result['error']}")
                
                logger.info(f"✅ Extracted {len(reviews)} reviews for Place ID {place_id}")
                return {"reviews": reviews}
            
            logger.warning("⚠️ Outscraper returned an empty or unexpected list format.")
            return {"reviews": []}

        except Exception as e:
            logger.error(f"🚨 Outscraper Client Critical Failure: {e}", exc_info=True)
            return {"reviews": []}

    async def close(self):
        await self.client.aclose()

class DummyReviewsClient:
    """Fallback if API Key is missing to prevent startup crash."""
    async def get_reviews(self, *args, **kwargs):
        logger.warning("⚠️ Running in DUMMY MODE. No real reviews will be fetched.")
        return {"reviews": []}
    async def close(self):
        pass

# ────────────────────────────────────────────────────────────────
# LIFESPAN & DATABASE AUTOMATION
# ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Database Initialization & SCHEMA_VERSION Logic
    try:
        engine: AsyncEngine = get_engine()
        async with engine.begin() as conn:
            # Create config table if it doesn't exist
            await conn.execute(text("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)"))
            
            # Check current version
            result = await conn.execute(text("SELECT value FROM config WHERE key='schema_version'"))
            row = result.first()
            db_version = row[0] if row else None

            # Automatic Rebuild if Schema is outdated
            if db_version != str(SCHEMA_VERSION):
                logger.warning(f"🔄 Schema Version Mismatch: {db_version} -> {SCHEMA_VERSION}. Rebuilding...")
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
                
                # Update version in DB
                await conn.execute(
                    text("INSERT INTO config (key, value) VALUES ('schema_version', :v) "
                         "ON CONFLICT (key) DO UPDATE SET value = :v"),
                    {"v": str(SCHEMA_VERSION)}
                )
                logger.info(f"✅ Schema successfully updated to v{SCHEMA_VERSION}")
            else:
                await conn.run_sync(Base.metadata.create_all)
                logger.info(f"✅ Database schema version {SCHEMA_VERSION} verified.")
    except Exception as e:
        logger.error(f"❌ Database Startup failed: {e}")

    # 2. Outscraper Client Setup
    # Priority: Railway Env Var > Local Settings
    api_key = os.getenv("OUTSCRAPER_API_KEY") or getattr(settings, "OUTSCRAPER_API_KEY", None)
    
    if api_key and len(api_key) > 10:
        app.state.google_reviews_client = OutscraperClient(api_key=api_key)
        app.state.api_status = "Connected"
        logger.info("🚀 Outscraper API Client: CONNECTED")
    else:
        app.state.google_reviews_client = DummyReviewsClient()
        app.state.api_status = "Disconnected (API Key Missing)"
        logger.error("🛑 Outscraper API Key is missing. Reviews will NOT sync.")

    yield
    # 3. Shutdown logic
    if hasattr(app.state, "google_reviews_client"):
        await app.state.google_reviews_client.close()

# ────────────────────────────────────────────────────────────────
# FASTAPI CONFIGURATION
# ────────────────────────────────────────────────────────────────
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# Standard Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static Files & Jinja2
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# ────────────────────────────────────────────────────────────────
# DIAGNOSTICS & SYSTEM ROUTES
# ────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request, "settings": settings})

@app.get("/health")
async def health(request: Request):
    """Health check for Railway monitoring."""
    return {
        "status": "ok",
        "api_client": getattr(request.app.state, "api_status", "unknown"),
        "database": "connected",
        "schema_version": SCHEMA_VERSION
    }

@app.get("/api/diagnostics/db-check")
async def db_diagnostic_check(company_id: int):
    """
    Directly check the database for data. 
    Use this if the dashboard looks empty!
    """
    async with get_session() as session:
        # 1. Total Count
        count_stmt = select(func.count(Review.id)).where(Review.company_id == company_id)
        count_res = await session.execute(count_stmt)
        total_reviews = count_res.scalar() or 0
        
        # 2. Latest/Earliest Review Date
        range_stmt = select(
            func.min(Review.google_review_time), 
            func.max(Review.google_review_time)
        ).where(Review.company_id == company_id)
        range_res = await session.execute(range_stmt)
        dates = range_res.first()
        
        return {
            "company_id": company_id,
            "reviews_in_database": total_reviews,
            "earliest_review_found": str(dates[0]) if dates[0] else "None",
            "latest_review_found": str(dates[1]) if dates[1] else "None",
            "api_status": getattr(app.state, "api_status", "unknown")
        }

# Include all application routes
app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)
