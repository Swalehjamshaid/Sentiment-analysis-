# filename: app/main.py

from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Optional, List

import httpx
from fastapi import FastAPI, Request, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Boolean, select, func
from sqlalchemy.ext.declarative import declarative_base
from passlib.context import CryptContext

# ---------------------------
# Logging
# ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("app.main")

# ---------------------------
# Settings
# ---------------------------
class Settings:
    APP_NAME = "MyFastAPIApp"
    SECRET_KEY = os.getenv("SECRET_KEY", "supersecret")
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/mydb")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    OUTSCRAPER_API_KEY = os.getenv("OUTSCRAPER_API_KEY", "")

settings = Settings()

# ---------------------------
# Database setup
# ---------------------------
engine: AsyncEngine = create_async_engine(settings.DATABASE_URL, echo=True, future=True)
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

Base = declarative_base()
SCHEMA_VERSION = 1
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------
# Models
# ---------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=func.now())

    def set_password(self, password: str):
        self.hashed_password = pwd_context.hash(password)

    def check_password(self, password: str) -> bool:
        return pwd_context.verify(password, self.hashed_password)

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    address = Column(String(500))
    latitude = Column(Float)
    longitude = Column(Float)
    phone = Column(String(50))
    website = Column(String(255))
    rating = Column(Float)
    reviews_count = Column(Integer, default=0)
    google_place_id = Column(String(255))
    is_active = Column(Boolean, default=True)

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, nullable=False)
    author_name = Column(String(255))
    text = Column(Text)
    rating = Column(Float)
    created_at = Column(DateTime, default=func.now())

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
                return {"reviews": data[0].get("reviews_data", [])}
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
# Lifespan
# ---------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database Schema v%s verified.", SCHEMA_VERSION)
    api_key = settings.OUTSCRAPER_API_KEY
    if api_key and len(api_key) > 10:
        app.state.reviews_client = OutscraperClient(api_key=api_key)
        logger.info("🚀 Outscraper Client: CONNECTED")
    else:
        logger.error("🛑 OUTSCRAPER_API_KEY missing.")
    yield
    if hasattr(app.state, "reviews_client"):
        await app.state.reviews_client.close()

# ---------------------------
# FastAPI App
# ---------------------------
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
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
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "user": None})

@app.post("/login")
async def login_post(request: Request, email: str = Form(...), password: str = Form(...), session_db: AsyncSession = Depends(get_session)):
    async with session_db as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        if not user or not user.check_password(password):
            return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})
        request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
        return RedirectResponse("/dashboard", status_code=303)

@app.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "user": None})

@app.post("/register")
async def register_post(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...), session_db: AsyncSession = Depends(get_session)):
    async with session_db as session:
        result = await session.execute(select(User).where(User.email == email))
        existing = result.scalars().first()
        if existing:
            return templates.TemplateResponse("register.html", {"request": request, "error": "Email already registered"})
        user = User(name=name, email=email)
        user.set_password(password)
        session.add(user)
        await session.commit()
        request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
        return RedirectResponse("/dashboard", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "google_api_key": settings.GOOGLE_API_KEY})

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

# ---------------------------
# Include routers
# ---------------------------
# Import routers here (no circular imports)
# If routers need db/session, pass get_session as dependency
# Example for reviews router
from fastapi import APIRouter

reviews_router = APIRouter(prefix="/api/reviews")

@reviews_router.get("/all")
async def get_reviews(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Review))
    return result.scalars().all()

app.include_router(reviews_router)

# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
