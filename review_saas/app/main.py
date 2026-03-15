# filename: app/main.py

from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Optional, List

import httpx
from fastapi import FastAPI, Request, Depends, Form, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.future import select

from app.core.config import settings
from app.core.db import get_engine, get_session
from app.core.models import Base, SCHEMA_VERSION, User

# Routers
from app.routes import auth as auth_routes
from app.routes import companies as companies_routes
from app.routes import dashboard as dashboard_routes
from app.routes import reviews as reviews_routes
from app.routes import exports as exports_routes
from app.routes import google_check as google_routes

# ---------------------------
# Logging Setup
# ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("app.main")

# ---------------------------
# Outscraper Client
# ---------------------------
class OutscraperClient:
    BASE_URL = "https://api.app.outscraper.com/maps/reviews"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))

    async def get_reviews(self, place_id: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        try:
            params = {"query": place_id, "limit": limit, "offset": offset, "async": "false"}
            headers = {"X-API-KEY": self.api_key}
            response = await self.client.get(self.BASE_URL, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                reviews = data[0].get("reviews_data", [])
                return {"reviews": reviews}
            return {"reviews": []}
        except Exception as e:
            logger.error("Outscraper API Error: %s", e, exc_info=True)
            return {"reviews": []}

    async def fetch_reviews(self, entity: Any, max_reviews: Optional[int] = None) -> List[dict[str, Any]]:
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

    # Outscraper Client Setup
    api_key = os.getenv("OUTSCRAPER_API_KEY") or getattr(settings, "OUTSCRAPER_API_KEY", None)
    if api_key and len(api_key) > 10:
        app.state.reviews_client = OutscraperClient(api_key=api_key)
        logger.info("🚀 Outscraper Client: CONNECTED")
    else:
        logger.error("🛑 OUTSCRAPER_API_KEY missing.")

    yield

    # Cleanup
    if hasattr(app.state, "reviews_client"):
        await app.state.reviews_client.close()

# ---------------------------
# FastAPI App Initialization
# ---------------------------
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# ---------------------------
# Auth Helpers
# ---------------------------
def get_current_user(request: Request) -> Optional[dict]:
    return request.session.get("user")

# ---------------------------
# Routes
# ---------------------------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/login")

# ---------------------------
# LOGIN
# ---------------------------
@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "user": None})

@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session_db: AsyncEngine = Depends(get_session),
):
    async with session_db() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        if not user or not user.check_password(password):
            return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})
        # Save session
        request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
        return RedirectResponse(url="/dashboard", status_code=303)

# ---------------------------
# REGISTRATION
# ---------------------------
@app.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "user": None})

@app.post("/register")
async def register_post(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    session_db: AsyncEngine = Depends(get_session),
):
    async with session_db() as session:
        # Check if user exists
        result = await session.execute(select(User).where(User.email == email))
        existing = result.scalars().first()
        if existing:
            return templates.TemplateResponse("register.html", {"request": request, "error": "Email already registered"})
        # Create user
        user = User(name=name, email=email)
        user.set_password(password)
        session.add(user)
        await session.commit()
        # Save session
        request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
        return RedirectResponse(url="/dashboard", status_code=303)

# ---------------------------
# DASHBOARD
# ---------------------------
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "google_api_key": settings.GOOGLE_API_KEY
    })

# ---------------------------
# Logout
# ---------------------------
@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

# ---------------------------
# Include routers
# ---------------------------
app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)
app.include_router(google_routes.router)

# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
