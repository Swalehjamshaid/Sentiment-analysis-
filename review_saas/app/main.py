# filename: app/main.py
from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncEngine
from app.core.config import settings
from app.core.db import get_engine, get_session
from app.core.models import Base, SCHEMA_VERSION, Company, Review
# Routers
from app.routes import auth as auth_routes
from app.routes import companies as companies_routes
from app.routes import dashboard as dashboard_routes
from app.routes import reviews as reviews_routes
from app.routes import exports as exports_routes

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

# -----------------------------------------------------------------------------
# Outscraper Client (Robust)
# -----------------------------------------------------------------------------
class OutscraperClient:
    """
    Handles connection to Outscraper Google Reviews API.
    Parses the nested list response and extracts 'reviews_data'.
    """
    BASE_URL = "https://api.app.outscraper.com/google-reviews"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))

    async def get_reviews(self, place_id: str, limit: int = 200, offset: int = 0) -> Dict[str, Any]:
        try:
            params = {
                "query": place_id,
                "limit": limit,
                "offset": offset,
                "async": "false", # synchronous mode
            }
            headers = {"X-API-KEY": self.api_key}
            logger.info("📡 Requesting Outscraper reviews for Place ID: %s", place_id)
            response = await self.client.get(self.BASE_URL, params=params, headers=headers)
            if response.status_code != 200:
                logger.error("❌ Outscraper API Error %s: %s", response.status_code, response.text)
                return {"reviews": []}
            data = response.json()
            # Expected top-level list -> item 0 -> "reviews_data"
            if isinstance(data, list) and data:
                q = data[0]
                reviews = q.get("reviews_data", [])
                if not reviews and q.get("error"):
                    logger.warning("⚠️ Outscraper error: %s", q["error"])
                logger.info("✅ Fetched %s reviews for %s", len(reviews), place_id)
                return {"reviews": reviews}
            logger.warning("⚠️ Outscraper returned unexpected format (not a list or empty).")
            return {"reviews": []}
        except Exception as e:
            logger.error("🚨 Outscraper Client Failure: %s", e, exc_info=True)
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

# -----------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1) DB setup + schema check/update
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
                logger.warning("🔄 Schema mismatch: DB v%s → v%s. Rebuilding...", db_version, SCHEMA_VERSION)
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
                # Upsert version
                await conn.execute(
                    text("""
                        INSERT INTO config (key, value)
                        VALUES ('schema_version', :v)
                        ON CONFLICT (key) DO UPDATE SET value = :v
                    """),
                    {"v": str(SCHEMA_VERSION)},
                )
                logger.info("✅ Schema rebuilt to v%s", SCHEMA_VERSION)
            else:
                # Ensure all tables exist if version is already correct
                await conn.run_sync(Base.metadata.create_all)
                logger.info("✅ Schema v%s verified.", SCHEMA_VERSION)
    except Exception as e:
        logger.error("❌ Database startup failed: %s", e, exc_info=True)

    # 2) Outscraper client init
    api_key = os.getenv("OUTSCRAPER_API_KEY") or getattr(settings, "OUTSCRAPER_API_KEY", None)
    if api_key and len(api_key) > 10:
        app.state.google_reviews_client = OutscraperClient(api_key=api_key)
        app.state.api_status = "Connected"
        logger.info("🚀 Outscraper Client: CONNECTED")
    else:
        app.state.google_reviews_client = DummyReviewsClient()
        app.state.api_status = "Disconnected (API Key Missing)"
        logger.error("🛑 OUTSCRAPER_API_KEY missing. Sync will NOT fetch real reviews.")

    # Secret key check (session cookies)
    if not getattr(settings, "SECRET_KEY", None):
        logger.error("🛑 SECRET_KEY is missing in settings. Session middleware will be insecure.")

    yield  # ---- app runs ----

    # 3) Shutdown cleanup
    if hasattr(app.state, "google_reviews_client"):
        try:
            await app.state.google_reviews_client.close()
        except Exception:  # best effort
            pass
        logger.info("Outscraper client closed.")

# -----------------------------------------------------------------------------
# FastAPI app
# -----------------------------------------------------------------------------
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # adjust as needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static & templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# -----------------------------------------------------------------------------
# Diagnostics & Health
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request, "settings": settings})

@app.get("/health")
async def health():
    """Simple health check (used by Railway/monitors)."""
    return {
        "status": "ok",
        "api_client": getattr(app.state, "api_status", "unknown"),
        "database": "connected",
        "schema_version": SCHEMA_VERSION,
    }

@app.get("/api/diagnostics/db-check")
async def db_diagnostic_check(company_id: int):
    """
    Quick check for data presence for a company.
    Example: /api/diagnostics/db-check?company_id=1
    """
    async with get_session() as session:
        total_reviews = (await session.execute(
            select(func.count(Review.id)).where(Review.company_id == company_id)
        )).scalar() or 0
        dates = (await session.execute(
            select(
                func.min(Review.google_review_time),
                func.max(Review.google_review_time),
            ).where(Review.company_id == company_id)
        )).first()
        return {
            "company_id": company_id,
            "reviews_in_database": int(total_reviews),
            "earliest_review": str(dates[0]) if dates and dates[0] else "None",
            "latest_review": str(dates[1]) if dates and dates[1] else "None",
            "api_status": getattr(app.state, "api_status", "unknown"),
        }

# Optional: quick template checker
@app.get("/__template_check")
async def __template_check(request: Request):
    try:
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "companies": [], "active_company_id": None},
        )
    except Exception as e:
        return Response(str(e), status_code=500)

# -----------------------------------------------------------------------------
# Routers
# -----------------------------------------------------------------------------
app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)

# -----------------------------------------------------------------------------
# Railway / production entry point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    
    # Railway sets PORT environment variable
    port = int(os.getenv("PORT", "8080"))
    host = "0.0.0.0"
    
    logger.info(f"Starting Uvicorn → http://{host}:{port}")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level="info",
        # Recommended for Railway (limits concurrency to avoid memory issues)
        workers=1,
        limit_concurrency=500,
        timeout_keep_alive=30,
    )
