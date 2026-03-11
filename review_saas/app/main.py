# filename: app/main.py
from __future__ import annotations

import logging
import os
import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# Core Configuration and Database Imports
from app.core.config import settings
from app.core.db import get_engine
from app.core.models import Base, SCHEMA_VERSION

# Route Imports (Requirement 13 Synchronization)
from app.routes import auth as auth_routes
from app.routes import companies as companies_routes
from app.routes import dashboard as dashboard_routes
from app.routes import reviews as reviews_routes
from app.routes import exports as exports_routes

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 1: Logging Configuration (Requirement 9)
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 2: Production Outscraper Client (Requirement 2 & 7)
# ──────────────────────────────────────────────────────────────────────────────
class OutscraperClient:
    """
    Optimized client for Google Reviews ingestion.
    Reuses a single AsyncClient to prevent socket exhaustion.
    """
    BASE_URL = "https://api.app.outscraper.com/google-reviews"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))

    async def fetch_reviews(self, place_id: str, limit: int = 200) -> Dict[str, Any]:
        """Method used by routes/reviews.py to ingest data."""
        try:
            params = {"query": place_id, "limit": limit, "async": "false"}
            headers = {"X-API-KEY": self.api_key}
            
            logger.info("📡 Outscraper API Fetch: Place ID %s", place_id)
            response = await self.client.get(self.BASE_URL, params=params, headers=headers)
            
            if response.status_code != 200:
                logger.error("❌ Outscraper API Error %s: %s", response.status_code, response.text)
                return {"reviews": []}
            
            data = response.json()
            if isinstance(data, list) and data:
                reviews = data[0].get("reviews_data", [])
                logger.info("✅ Successfully retrieved %s reviews", len(reviews))
                return {"reviews": reviews}
            
            return {"reviews": []}
        except Exception as e:
            logger.error("🚨 Outscraper Client Failure: %s", e, exc_info=True)
            return {"reviews": []}

    async def close(self):
        await self.client.aclose()

class DummyReviewsClient:
    """Fallback client if API Key is missing."""
    async def fetch_reviews(self, *args, **kwargs):
        logger.warning("⚠️ DUMMY MODE ACTIVE: Simulation only.")
        return {"reviews": []}
    async def close(self): pass

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 3: Application Lifespan (Requirement 1)
# ──────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Database Initialization & Version Verification
    try:
        engine: AsyncEngine = get_engine()
        async with engine.begin() as conn:
            # Table for schema tracking
            await conn.execute(text("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)"))
            
            # Verify version to prevent crashes on Railway
            result = await conn.execute(text("SELECT value FROM config WHERE key='schema_version'"))
            row = result.first()
            db_version = row[0] if row else None

            if db_version != str(SCHEMA_VERSION):
                logger.warning("🔄 Schema Mismatch. Rebuilding for v%s...", SCHEMA_VERSION)
                await conn.run_sync(Base.metadata.create_all)
                await conn.execute(
                    text("INSERT INTO config (key, value) VALUES ('schema_version', :v) ON CONFLICT (key) DO UPDATE SET value = :v"),
                    {"v": str(SCHEMA_VERSION)}
                )
            else:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Database Schema v%s verified.", SCHEMA_VERSION)
    except Exception as e:
        logger.error("❌ DB Startup Failed: %s", e)

    # Ingestion Client Setup
    api_key = os.getenv("OUTSCRAPER_API_KEY") or settings.OUTSCRAPER_API_KEY
    if api_key and len(api_key) > 10:
        app.state.google_reviews_client = OutscraperClient(api_key=api_key)
        app.state.api_status = "Connected"
        logger.info("🚀 External Ingestion Service: CONNECTED")
    else:
        app.state.google_reviews_client = DummyReviewsClient()
        app.state.api_status = "Disconnected (Check API Key)"
        logger.warning("🛑 Outscraper key missing.")

    yield
    # Shutdown
    if hasattr(app.state, "google_reviews_client"):
        await app.state.google_reviews_client.close()

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 4: FastAPI Core Definition
# ──────────────────────────────────────────────────────────────────────────────
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# Middleware (Requirement 13)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Assets
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 5: Core Endpoints (Dashboard Sync)
# ──────────────────────────────────────────────────────────────────────────────
def get_current_user(request: Request):
    return request.session.get("user")

@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request, "settings": settings})

@app.get("/health")
async def health_check():
    return {"status": "ok", "api": getattr(app.state, "api_status", "unknown"), "v": SCHEMA_VERSION}

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})

@app.post("/login")
async def login_handler(request: Request):
    # Standard redirect for your testing (Rai Jamshaid admin profile)
    user = {"id": 1, "email": "roy.jamshaid@gmail.com", "name": "Rai Jamshaid"}
    request.session["user"] = user
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/logout")
async def logout_handler(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 6: Router Registration (Requirement 13)
# ──────────────────────────────────────────────────────────────────────────────
app.include_router(auth_routes.router)
app.include_router(companies_routes.router)  # Handles /api/companies & /api/google_autocomplete
app.include_router(dashboard_routes.router)  # Handles /api/dashboard/...
app.include_router(reviews_routes.router)    # Handles /api/reviews
app.include_router(exports_routes.router)    # Handles CSV/PDF/XLSX exports

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), log_level="info")
