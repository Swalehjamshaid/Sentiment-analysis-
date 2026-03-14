# filename: app/main.py

from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, List

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
from app.core.db import get_engine
from app.core.models import Base, SCHEMA_VERSION, Company, Review

# Routers
from app.routes import auth as auth_routes
from app.routes import companies as companies_routes
from app.routes import dashboard as dashboard_routes
from app.routes import reviews as reviews_routes
from app.routes import exports as exports_routes
from app.routes import google_check as google_routes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("app.main")

# ---------------------------
# FIXED: Outscraper Client
# ---------------------------
class OutscraperClient:
    # FIX: Changed endpoint from /google-reviews to /maps/reviews
    BASE_URL = "https://api.app.outscraper.com/maps/reviews"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))

    async def get_reviews(self, place_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        try:
            params = {
                "query": place_id, 
                "limit": limit, 
                "offset": offset, 
                "async": "false"
            }
            headers = {"X-API-KEY": self.api_key}
            
            logger.info("📡 Requesting Outscraper reviews for Place ID: %s", place_id)
            response = await self.client.get(self.BASE_URL, params=params, headers=headers)
            
            if response.status_code != 200:
                logger.error("❌ Outscraper API Error %s: %s", response.status_code, response.text)
                return {"reviews": []}
            
            data = response.json()
            # Outscraper returns a list of queries; we need the first result
            if isinstance(data, list) and len(data) > 0:
                result_block = data[0]
                reviews = result_block.get("reviews_data", [])
                logger.info("✅ Successfully parsed %s reviews from Outscraper payload", len(reviews))
                return {"reviews": reviews}
                
            return {"reviews": []}
        except Exception as e:
            logger.error("🚨 Outscraper Client Failure: %s", e, exc_info=True)
            return {"reviews": []}

    async def fetch_reviews(self, entity: Any, max_reviews: Optional[int] = None) -> List[Dict[str, Any]]:
        place_id = getattr(entity, "google_place_id", entity if isinstance(entity, str) else None)
        if not place_id:
            return []
        limit = max_reviews or 100
        result = await self.get_reviews(place_id, limit=limit)
        return result.get("reviews", [])

    async def close(self):
        await self.client.aclose()

# ---------------------------
# Lifespan & App Setup
# ---------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Database Initialization
    try:
        engine: AsyncEngine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Database Schema v%s verified.", SCHEMA_VERSION)
    except Exception as e:
        logger.error("❌ Database startup failed: %s", e)

    # API Client Setup
    api_key = os.getenv("OUTSCRAPER_API_KEY") or getattr(settings, "OUTSCRAPER_API_KEY", None)
    if api_key and len(api_key) > 10:
        app.state.reviews_client = OutscraperClient(api_key=api_key)
        logger.info("🚀 Outscraper Client: CONNECTED")
    else:
        logger.error("🛑 OUTSCRAPER_API_KEY missing.")

    yield
    if hasattr(app.state, "reviews_client"):
        await app.state.reviews_client.close()

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Auth Helper
def get_current_user(request: Request) -> Optional[dict]:
    return request.session.get("user")

# Routes
@app.get("/health")
async def health():
    return {"status": "ok", "database": "connected", "schema": SCHEMA_VERSION}

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, "google_api_key": settings.GOOGLE_API_KEY
    })

@app.post("/login")
async def login_post(request: Request):
    user = {"id": 1, "email": "roy.jamshaid@gmail.com", "name": "Swaleh"}
    request.session["user"] = user
    return RedirectResponse(url="/dashboard", status_code=303)

app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)
app.include_router(google_routes.router)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
