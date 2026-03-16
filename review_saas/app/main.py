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
from sqlalchemy import select  # SQLAlchemy 2.x style
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import init_models, get_session  # unified DB init & session dependency
from app.core.models import User  # keep as is; assumes methods on model for auth

# ---------------------------
# Logging Setup
# ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

# ---------------------------
# Outscraper Client (scoped)
# ---------------------------
class OutscraperClient:
    """
    Minimal async client to fetch reviews from Outscraper.
    NOTE: The endpoint here uses '/maps/reviews' to match your existing code.
          If you standardize on v3 elsewhere, consider switching to '/maps/reviews-v3'.
    """
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
    # Initialize database schema (prefer Alembic in production)
    try:
        await init_models()
        logger.info("✅ Database schema initialized.")
    except Exception as e:
        logger.error("❌ Database startup failed: %s", e, exc_info=True)

    # Outscraper client (optional)
    api_key = (
        os.getenv("OUTSCRAPER_API_KEY")
        or getattr(settings, "OUTSCRAPER_API_KEY", None)
        or ""
    )
    if api_key and len(api_key) > 10:
        app.state.reviews_client = OutscraperClient(api_key=api_key)
        logger.info("🚀 Outscraper Client: CONNECTED")
    else:
        logger.warning("ℹ️ OUTSCRAPER_API_KEY not provided; review sync endpoints may be disabled.")

    # App is ready
    yield

    # Graceful shutdown
    if hasattr(app.state, "reviews_client"):
        try:
            await app.state.reviews_client.close()
        except Exception:
            logger.warning("Failed to close Outscraper client gracefully.", exc_info=True)

# ---------------------------
# FastAPI App Initialization
# ---------------------------
app = FastAPI(title=getattr(settings, "APP_NAME", "ReviewSaaS API"), lifespan=lifespan)

# CORS (tighten in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sessions
_secret_key = (
    getattr(settings, "SECRET_KEY", None)
    or os.getenv("SECRET_KEY")
    or "dev-insecure-secret"  # dev fallback; replace in prod
)
app.add_middleware(SessionMiddleware, secret_key=_secret_key)

# Static & Templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# ---------------------------
# Auth Helpers
# ---------------------------
def get_current_user(request: Request) -> Optional[dict]:
    return request.session.get("user")

# ---------------------------
# Views
# ---------------------------
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/login")

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "user": None})

@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session_db: AsyncSession = Depends(get_session),
):
    # Using the DB dependency directly (no nested 'async with'; the dependency handles scope)
    result = await session_db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    # Expecting your User model to implement 'check_password'
    if not user or not getattr(user, "check_password", lambda *_: False)(password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})
    request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "user": None})

@app.post("/register")
async def register_post(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    session_db: AsyncSession = Depends(get_session),
):
    result = await session_db.execute(select(User).where(User.email == email))
    existing = result.scalars().first()
    if existing:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Email already registered"})
    user = User(name=name, email=email)
    # Expecting your User model to implement 'set_password'
    if hasattr(user, "set_password"):
        user.set_password(password)
    else:
        # Fallback (DO NOT use in production; ensure proper password hashing in your model)
        user.hashed_password = password
    session_db.add(user)
    await session_db.commit()
    # reload id
    await session_db.refresh(user)
    request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    google_api_key = (
        getattr(settings, "GOOGLE_API_KEY", None)
        or os.getenv("GOOGLE_API_KEY")
        or ""
    )
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "google_api_key": google_api_key,
        },
    )

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

# ---------------------------
# Include Routers (fault-tolerant)
# ---------------------------
def _include_router_safe(module_path: str, attr: str = "router") -> None:
    try:
        mod = __import__(module_path, fromlist=[attr])
        router = getattr(mod, attr, None)
        if router is not None:
            app.include_router(router)
            logger.info("🔗 Included router: %s.%s", module_path, attr)
        else:
            logger.warning("Router attribute '%s' not found in %s", attr, module_path)
    except Exception as e:
        logger.warning("Skipping router %s due to import error: %s", module_path, e)

# Core routers you mentioned; included if present in your codebase
_include_router_safe("app.routes.auth")
_include_router_safe("app.routes.companies")
_include_router_safe("app.routes.dashboard")
_include_router_safe("app.routes.reviews")
_include_router_safe("app.routes.exports")
_include_router_safe("app.routes.google_check")

# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
