from __future__ import annotations
import logging
import os
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

from app.core.config import settings
from app.core.db import get_engine, get_session
from app.core.models import Base, SCHEMA_VERSION, Company, Review

# Routers
from app.routes import auth as auth_routes
from app.routes import companies as companies_routes
from app.routes import dashboard as dashboard_routes
from app.routes import reviews as reviews_routes
from app.routes import exports as exports_routes

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")


# Outscraper Client
class OutscraperClient:
    BASE_URL = "https://api.app.outscraper.com/google-reviews"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))

    async def get_reviews(self, place_id: str, limit: int = 200, offset: int = 0) -> Dict[str, Any]:
        try:
            params = {"query": place_id, "limit": limit, "offset": offset, "async": "false"}
            headers = {"X-API-KEY": self.api_key}
            logger.info("📡 Requesting Outscraper reviews for Place ID: %s", place_id)
            response = await self.client.get(self.BASE_URL, params=params, headers=headers)
            if response.status_code != 200:
                logger.error("❌ Outscraper API Error %s: %s", response.status_code, response.text)
                return {"reviews": []}
            data = response.json()
            if isinstance(data, list) and data:
                q = data[0]
                reviews = q.get("reviews_data", [])
                if not reviews and q.get("error"):
                    logger.warning("⚠️ Outscraper error: %s", q["error"])
                logger.info("✅ Fetched %s reviews for %s", len(reviews), place_id)
                return {"reviews": reviews}
            logger.warning("⚠️ Outscraper returned unexpected format.")
            return {"reviews": []}
        except Exception as e:
            logger.error("🚨 Outscraper Client Failure: %s", e, exc_info=True)
            return {"reviews": []}

    async def close(self):
        await self.client.aclose()


# Dummy client
class DummyReviewsClient:
    async def get_reviews(self, *args, **kwargs):
        logger.warning("⚠️ DUMMY MODE: No real reviews will be fetched.")
        return {"reviews": []}

    async def close(self):
        pass


# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB setup
    try:
        engine: AsyncEngine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """))
            result = await conn.execute(text("SELECT value FROM config WHERE key='schema_version'"))
            row = result.first()
            db_version = row[0] if row else None
            if db_version != str(SCHEMA_VERSION):
                logger.warning("🔄 Schema mismatch: DB v%s → v%s. Rebuilding...", db_version, SCHEMA_VERSION)
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
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
                await conn.run_sync(Base.metadata.create_all)
                logger.info("✅ Schema v%s verified.", SCHEMA_VERSION)
    except Exception as e:
        logger.error("❌ Database startup failed: %s", e, exc_info=True)

    # Outscraper client
    api_key = os.getenv("OUTSCRAPER_API_KEY") or getattr(settings, "OUTSCRAPER_API_KEY", None)
    if api_key and len(api_key) > 10:
        app.state.reviews_client = OutscraperClient(api_key=api_key)
        app.state.api_status = "Connected"
        logger.info("🚀 Outscraper Client: CONNECTED")
    else:
        app.state.reviews_client = DummyReviewsClient()
        app.state.api_status = "Disconnected (API Key Missing)"
        logger.error("🛑 OUTSCRAPER_API_KEY missing.")

    # Secret key check
    if not getattr(settings, "SECRET_KEY", None):
        logger.error("🛑 SECRET_KEY is missing in settings.")

    yield

    # Close client gracefully
    if hasattr(app.state, "reviews_client"):
        try:
            await app.state.reviews_client.close()
        except Exception:
            pass
        logger.info("Outscraper client closed.")


# FastAPI app
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static & templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# Current user
def get_current_user(request: Request) -> Optional[dict]:
    return request.session.get("user")


# Landing & dashboard
@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request, "settings": settings})


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "api_client": getattr(app.state, "api_status", "unknown"),
        "database": "connected",
        "schema_version": SCHEMA_VERSION,
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})


# Login route
@app.post("/login", response_class=RedirectResponse)
async def login_post(request: Request):
    user = {"id": 1, "email": "roy.jamshaid@gmail.com", "name": "Rai Jamshaid"}
    request.session["user"] = user
    request.session["user_id"] = user["id"]
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


# Include routers
app.include_router(auth_routes.router)
app.include_router(companies_routes.router)  # <-- fixes /api/google_autocomplete 404
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)


# Railway entry point
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    host = "0.0.0.0"
    logger.info(f"Starting Uvicorn on http://{host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port, log_level="info", workers=1, limit_concurrency=300, timeout_keep_alive=30)
