import sys
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional, Tuple

from fastapi import FastAPI, Request, Depends, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy import select
from passlib.context import CryptContext

# Absolute path resolution to fix importlib/uvicorn issues on Railway
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.db import init_models, get_db, SessionLocal, engine
from app.core import models
from app.core.models import User, SCHEMA_VERSION, Config as ConfigModel
from app.routes import auth, companies, dashboard, reviews, exports, google_check

# Initialize password context and logger
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("app.main")

async def _get_stored_schema_version(session):
    """Internal helper to read the current database schema version."""
    res = await session.execute(select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION"))
    row = res.scalar_one_or_none()
    return row.value if row else None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan manager to handle startup and shutdown.
    Implements Stegman Rules for schema versioning and auto-reset.
    """
    logger.info("🚀 Review Intel AI: Lifespan Startup...")
    await init_models()
    async with SessionLocal() as session:
        old_v = await _get_stored_schema_version(session)
        if old_v != str(SCHEMA_VERSION):
            logger.warning(f"🧩 SCHEMA CHANGE: {old_v} -> {SCHEMA_VERSION}. Resetting...")
            async with engine.begin() as conn:
                await conn.run_sync(models.Base.metadata.drop_all)
                await conn.run_sync(models.Base.metadata.create_all)
            
            # Update schema version record
            res = await session.execute(select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION"))
            row = res.scalar_one_or_none()
            if row:
                row.value = str(SCHEMA_VERSION)
            else:
                session.add(ConfigModel(key="SCHEMA_VERSION", value=str(SCHEMA_VERSION)))
            await session.commit()
    yield
    logger.info("🛑 Review Intel AI: Lifespan Shutdown...")

# Initialize FastAPI App
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# Middleware Configuration
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static and Template Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_path = os.path.join(BASE_DIR, "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- Core Routes ---
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login")

@app.post("/login")
async def handle_login(request: Request, email: str = Form(...), password: str = Form(...), db=Depends(get_db)):
    """Handles secure user login with verification check."""
    email_clean = email.strip().lower()
    res = await db.execute(select(User).where(User.email == email_clean))
    user = res.scalars().first()
    
    if user and pwd_context.verify(password, user.hashed_password):
        if not user.is_verified:
            return templates.TemplateResponse("login.html", {
                "request": request, 
                "error": "Account unverified. Please check your email for the link."
            })
        
        request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
        return RedirectResponse("/dashboard", status_code=303)
    
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials."})

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# --- Router Mounting ---
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])
app.include_router(exports.router, prefix="/api", tags=["exports"])
app.include_router(google_check.router, prefix="/api", tags=["google_check"])

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
