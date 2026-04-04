# filename: review_saas/app/main.py
import sys
import os
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Depends, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

# --- 1. PATH RESOLUTION (Strict Alignment for your structure) ---
CURRENT_FILE_PATH = os.path.abspath(__file__)
APP_DIR = os.path.dirname(CURRENT_FILE_PATH)        # path to .../app/
PACKAGE_DIR = os.path.dirname(APP_DIR)             # path to .../review_saas/
ROOT_DIR = os.path.dirname(PACKAGE_DIR)            # Project Root

# Add paths to sys.path to ensure modules are discoverable by the loader
for path in [ROOT_DIR, PACKAGE_DIR, APP_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

# Core internal imports
try:
    from app.core.config import settings
    from app.core.db import init_models, get_db, SessionLocal, engine
    from app.core import models
    from app.core.models import User, SCHEMA_VERSION, Config as ConfigModel
    from app.routes import auth, companies, dashboard, reviews, exports, google_check
except ImportError as e:
    logger = logging.getLogger("app.main")
    print(f"CRITICAL IMPORT ERROR: {e}. Check your __init__.py files.")
    raise

# --- 2. LOGGING & SECURITY ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("app.main")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- 3. DATABASE HELPERS ---
async def _get_stored_schema_version(session: AsyncSession) -> Optional[str]:
    try:
        res = await session.execute(select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION"))
        row = res.scalar_one_or_none()
        return row.value if row else None
    except Exception: return None

async def _update_stored_schema_version(session: AsyncSession, version: str):
    res = await session.execute(select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION"))
    row = res.scalar_one_or_none()
    if row: row.value = version
    else: session.add(ConfigModel(key="SCHEMA_VERSION", value=version))
    await session.commit()

# --- 4. LIFESPAN (FIX FOR THE UVICORN 68 ERROR) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Review Intel AI...")
    try:
        # Give Railway Postgres 2 seconds to accept the private domain connection
        await asyncio.sleep(2)
        
        # Step 1: Initialize DB tables safely
        await init_models()
        
        # Step 2: Handle Schema Transitions
        async with SessionLocal() as session:
            try:
                old_v = await _get_stored_schema_version(session)
                new_v = str(SCHEMA_VERSION)
                
                if old_v != new_v:
                    logger.warning(f"🧩 Schema Mismatch: {old_v} -> {new_v}. Aligning...")
                    async with engine.begin() as conn:
                        await conn.run_sync(models.Base.metadata.drop_all)
                        await conn.run_sync(models.Base.metadata.create_all)
                    await _update_stored_schema_version(session, new_v)
                else:
                    logger.info(f"✅ Schema verified: {new_v}")
                
                app.state.schema_version = new_v
            except Exception as db_e:
                logger.warning(f"⚠️ DB handshake delayed: {db_e}")
                app.state.schema_version = str(SCHEMA_VERSION)
        
    except Exception as e:
        # This catch prevents the asyncio loop from collapsing
        logger.error(f"❌ Startup Sequence Alignment Issue: {str(e)}")
    
    yield
    logger.info("🛑 Shutting down...")

# --- 5. APP INIT & MIDDLEWARE ---
app = FastAPI(title=getattr(settings, "APP_NAME", "Review SaaS AI"), lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(SessionMiddleware, secret_key=getattr(settings, "SECRET_KEY", "fallback-secret-2026"))

# --- 6. STATIC & TEMPLATES (Absolute Path Alignment) ---
app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))

# --- 7. CORE ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@app.post("/login")
async def handle_login(request: Request, email: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    email_clean = email.strip().lower()
    result = await db.execute(select(User).where(User.email == email_clean))
    user = result.scalars().first()
    
    if user and pwd_context.verify(password, user.hashed_password):
        request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
        return RedirectResponse("/dashboard", status_code=303)
    
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid email or password."})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    if not request.session.get("user"): return RedirectResponse("/login")
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "user": request.session.get("user"),
        "schema_version": getattr(app.state, "schema_version", "Unknown")
    })

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# --- 8. MOUNT ROUTERS ---
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])
app.include_router(exports.router, prefix="/api", tags=["exports"])
app.include_router(google_check.router, prefix="/api", tags=["google_check"])

if __name__ == "__main__":
    import uvicorn
    # Final entry point for Railway/Docker
    uvicorn.run("review_saas.app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), reload=False)
