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
    BASE_URL = "https://api.app.outscraper.com/google-reviews"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.http = httpx.Client(timeout=60) # Increased timeout for large batches

    def get_reviews(self, place_id: str, limit: int, offset: int = 0) -> Dict[str, List[Dict[str, Any]]]:
        try:
            params = {
                "query": place_id,
                "amount": limit,
                "offset": offset,
            }
            headers = {"X-API-KEY": self.api_key}
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

class DummyReviewsClient:
    def get_reviews(self, place_id: str, limit: int, offset: int = 0):
        logger.warning("[DummyReviewsClient] ACTIVE - No real data will be fetched.")
        return {"reviews": []}

# ────────────────────────────────────────────────────────────────
# LIFESPAN
# ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        engine: AsyncEngine = get_engine()
        async with engine.begin() as conn:
            # Schema logic
            result = await conn.execute(text("SELECT value FROM config WHERE key='schema_version'"))
            row = result.first()
            db_version = row[0] if row else None

            if db_version != SCHEMA_VERSION:
                logger.warning(f"Rebuilding Database: {db_version} -> {SCHEMA_VERSION}")
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
                await conn.execute(text("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)"))
                await conn.execute(text("INSERT INTO config (key, value) VALUES ('schema_version', :v)"), {"v": SCHEMA_VERSION})
            else:
                await conn.run_sync(Base.metadata.create_all)

        # API Key Setup
        api_key = os.getenv("OUTSCRAPER_API_KEY") or os.getenv("OUTSCAPTER_KEY")
        if api_key and len(api_key) > 10:
            app.state.google_reviews_client = OutscraperClient(api_key=api_key)
            app.state.api_status = "Connected"
        else:
            app.state.google_reviews_client = DummyReviewsClient()
            app.state.api_status = "Disconnected (Dummy Mode)"

    except Exception as e:
        logger.error(f"Startup failed: {e}")
    yield

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# Middleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request, "settings": settings})

app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)

@app.get("/health")
async def health(request: Request):
    return {
        "status": "ok",
        "api_client": request.app.state.api_status,
        "database": "connected"
    }
