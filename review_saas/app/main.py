# filename: app/main.py

from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Optional, List

import httpx
from fastapi import FastAPI, Request, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.ext.declarative import declarative_base

# ---------------------------
# Logging Setup
# ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("app.main")

# ---------------------------
# Settings
# ---------------------------
class Settings:
    APP_NAME = "MyApp"
    SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
    OUTSCRAPER_API_KEY = os.getenv("OUTSCRAPER_API_KEY", "")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

settings = Settings()

# ---------------------------
# Database Setup
# ---------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres")
engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

# ---------------------------
# Models
# ---------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)

    def set_password(self, password: str):
        import hashlib
        self.password_hash = hashlib.sha256(password.encode()).hexdigest()

    def check_password(self, password: str) -> bool:
        import hashlib
        return self.password_hash == hashlib.sha256(password.encode()).hexdigest()

# ---------------------------
# Database Session Dependency
# ---------------------------
async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session

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

    async def close(self):
        await self.client.aclose()

# ---------------------------
# Lifespan & App Setup
# ---------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Database initialized")
    except Exception as e:
        logger.error("❌ Database startup failed: %s", e)

    # Outscraper client
    if settings.OUTSCRAPER_API_KEY and len(settings.OUTSCRAPER_API_KEY) > 10:
        app.state.reviews_client = OutscraperClient(settings.OUTSCRAPER_API_KEY)
        logger.info("🚀 Outscraper Client connected")
    else:
        logger.error("🛑 OUTSCRAPER_API_KEY missing")

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

# Login/Register
@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "user": None})

@app.post("/login")
async def login_post(request: Request, email: str = Form(...), password: str = Form(...), session_db: AsyncSession = Depends(get_session)):
    result = await session_db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if not user or not user.check_password(password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})
    request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "user": None})

@app.post("/register")
async def register_post(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...), session_db: AsyncSession = Depends(get_session)):
    result = await session_db.execute(select(User).where(User.email == email))
    existing = result.scalars().first()
    if existing:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Email already registered"})
    user = User(name=name, email=email)
    user.set_password(password)
    session_db.add(user)
    await session_db.commit()
    request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
    return RedirectResponse(url="/dashboard", status_code=303)

# Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "google_api_key": settings.GOOGLE_API_KEY
    })

# Logout
@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

# Reviews Route Example
@app.get("/reviews")
async def get_reviews(request: Request):
    client: OutscraperClient = app.state.reviews_client
    place_id = request.query_params.get("place_id")
    if not place_id:
        return {"reviews": []}
    reviews = await client.get_reviews(place_id)
    return reviews

# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
