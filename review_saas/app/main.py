# filename: app/main.py
from __future__ import annotations

import logging
import os
import sys
import secrets
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, List

import httpx
from fastapi import FastAPI, Request, Depends, HTTPException, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# --------------------------- Absolute Path Resolution ---------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)

if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

def resolve_path(folder_name: str) -> str:
    """Check current and parent directories for the required folder."""
    local_path = os.path.join(CURRENT_DIR, folder_name)
    parent_path = os.path.join(PARENT_DIR, folder_name)
    if os.path.exists(local_path):
        return local_path
    return parent_path

TEMPLATE_DIR = resolve_path("templates")
STATIC_DIR = resolve_path("static")

# --------------------------- Core Imports ---------------------------
from app.core.config import settings
from app.core.db import get_engine
from app.core.models import Base, SCHEMA_VERSION, Company, Review

# --------------------------- Routers ---------------------------
from app.routes import auth as auth_routes
from app.routes import companies as companies_routes
from app.routes import dashboard as dashboard_routes
from app.routes import reviews as reviews_routes
from app.routes import exports as exports_routes
from app.routes import google_check as google_routes

# --------------------------- Logging ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

# --------------------------- Magic Link Token Store ---------------------------
# In production, use Redis or a DB table. For now, we use a global dict.
# Structure: { "token_id": {"email": "...", "expires": datetime} }
MAGIC_TOKENS: Dict[str, Dict[str, Any]] = {}

# --------------------------- Outscraper Client ---------------------------
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

class DummyReviewsClient:
    async def fetch_reviews(self, *args, **kwargs) -> List[Dict[str, Any]]:
        logger.warning("⚠️ DUMMY MODE: No real reviews will be fetched.")
        return []
    async def close(self): 
        pass

# --------------------------- Lifespan ---------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        engine: AsyncEngine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)"))
            result = await conn.execute(text("SELECT value FROM config WHERE key='schema_version'"))
            row = result.first()
            db_version = row[0] if row else None
            
            if db_version != str(SCHEMA_VERSION):
                logger.warning("🔄 Schema mismatch: DB v%s → v%s. Rebuilding...", db_version, SCHEMA_VERSION)
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
                await conn.execute(
                    text("INSERT INTO config (key, value) VALUES ('schema_version', :v) ON CONFLICT (key) DO UPDATE SET value = :v"),
                    {"v": str(SCHEMA_VERSION)},
                )
                logger.info("✅ Schema rebuilt to v%s", SCHEMA_VERSION)
            else:
                await conn.run_sync(Base.metadata.create_all)
                logger.info("✅ Schema v%s verified.", SCHEMA_VERSION)
    except Exception as e:
        logger.error("❌ Database startup failed: %s", e, exc_info=True)

    api_key = os.getenv("OUTSCRAPER_API_KEY") or getattr(settings, "OUTSCRAPER_API_KEY", None)
    if api_key and len(api_key) > 10:
        app.state.reviews_client = OutscraperClient(api_key=api_key)
        app.state.api_status = "Connected"
    else:
        app.state.reviews_client = DummyReviewsClient()
        app.state.api_status = "Disconnected (API Key Missing)"

    yield
    if hasattr(app.state, "reviews_client"):
        await app.state.reviews_client.close()

# --------------------------- App Setup ---------------------------
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

def get_current_user(request: Request) -> Optional[dict]:
    return request.session.get("user")

# --------------------------- Auth & Magic Link Routes ---------------------------

@app.get("/", response_class=HTMLResponse)
async def root_entry(request: Request, user: Optional[dict] = Depends(get_current_user)):
    """First step: Redirect to login if no session exists."""
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={})

@app.post("/login")
async def handle_magic_link_request(
    request: Request, 
    email: str = Form(...), 
    password: str = Form(...)
):
    """Step 2: Verify credentials and 'send' magic link."""
    # Hardcoded check for your email and a temporary admin password
    if email == "roy.jamshaid@gmail.com" and password == "admin123":
        token = secrets.token_urlsafe(32)
        MAGIC_TOKENS[token] = {
            "email": email,
            "expires": datetime.now() + timedelta(minutes=15)
        }
        
        # In a real setup, you would trigger your email sending function here.
        # The link would be: https://your-domain.com/verify?token={token}
        logger.info("🔑 MAGIC LINK CREATED for %s: /verify?token=%s", email, token)
        
        return templates.TemplateResponse(
            request=request, 
            name="login.html", 
            context={"message": "✅ Magic link generated! Check your server logs/email."}
        )
    
    return templates.TemplateResponse(
        request=request, 
        name="login.html", 
        context={"error": "Invalid email or password."}
    )

@app.get("/verify")
async def verify_magic_link(request: Request, token: str):
    """Step 3: User clicks the link, we verify and start the session."""
    token_data = MAGIC_TOKENS.get(token)
    
    if not token_data or token_data["expires"] < datetime.now():
        return templates.TemplateResponse(
            request=request, 
            name="login.html", 
            context={"error": "The magic link is invalid or has expired."}
        )
    
    # Start Session
    user = {"id": 1, "email": token_data["email"], "name": "Swaleh"}
    request.session["user"] = user
    
    # Clean up token
    del MAGIC_TOKENS[token]
    
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse(
        request=request, 
        name="dashboard.html", 
        context={
            "user": user,
            "google_api_key": settings.GOOGLE_API_KEY
        }
    )

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

# --------------------------- Other Routes ---------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok", 
        "api_client": getattr(app.state, "api_status", "unknown"), 
        "database": "connected", 
        "schema_version": SCHEMA_VERSION,
        "resolved_template_dir": TEMPLATE_DIR
    }

# Include All Routers
app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)
app.include_router(google_routes.router)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
