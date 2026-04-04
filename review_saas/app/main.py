import sys
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional, Tuple, Dict, Any

from fastapi import FastAPI, Request, Depends, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

# --- 1. PATH RESOLUTION (Optimized for Docker/Railway) ---
# Ensure we can find the 'app' package regardless of how uvicorn is called
CURRENT_FILE_PATH = os.path.abspath(__file__)
APP_DIR = os.path.dirname(CURRENT_FILE_PATH)
ROOT_DIR = os.path.dirname(APP_DIR)

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Core internal imports - Ensure these exist in your /app/core folder
try:
    from app.core.config import settings
    from app.core.db import init_models, get_db, SessionLocal, engine
    from app.core import models
    from app.core.models import User, SCHEMA_VERSION, Config as ConfigModel
    
    # Router imports
    from app.routes import auth, companies, dashboard, reviews, exports, google_check
except ImportError as e:
    # This will catch exactly which file is missing during deployment
    print(f"CRITICAL IMPORT ERROR: {e}")
    raise

# --- 2. LOGGING & SECURITY ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- 3. DATABASE HELPERS ---
async def _get_stored_schema_version(session: AsyncSession) -> Optional[str]:
    try:
        res = await session.execute(
            select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION")
        )
        row = res.scalar_one_or_none()
        return row.value if row else None
    except Exception:
        return None

async def _update_stored_schema_version(session: AsyncSession, version: str):
    res = await session.execute(
        select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION")
    )
    row = res.scalar_one_or_none()
    if row:
        row.value = version
    else:
        session.add(ConfigModel(key="SCHEMA_VERSION", value=version))
    await session.commit()

# --- 4. LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Review Intel AI...")
    try:
        await init_models()
        async with SessionLocal() as session:
            old_v = await _get_stored_schema_version(session)
            new_v = str(SCHEMA_VERSION)
            
            if old_v != new_v:
                logger.warning(f"🧩 Schema Mismatch: {old_v} -> {new_v}. Resetting...")
                async with engine.begin() as conn:
                    await conn.run_sync(models.Base.metadata.drop_all)
                    await conn.run_sync(models.Base.metadata.create_all)
                await _update_stored_schema_version(session, new_v)
            else:
                logger.info(f"✅ Schema verified: {new_v}")
        app.state.schema_version = new_v
    except Exception as e:
        logger.error(f"❌ Lifespan Error: {str(e)}")
    yield
    logger.info("🛑 Shutting down...")

# --- 5. APP INIT & MIDDLEWARE ---
app = FastAPI(
    title=getattr(settings, "APP_NAME", "Review SaaS AI"), 
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)
app.add_middleware(
    SessionMiddleware, 
    secret_key=getattr(settings, "SECRET_KEY", "fallback-very-secret-key")
)

# --- 6. STATIC & TEMPLATES ---
# Better path handling for templates/static
static_dir = os.path.join(APP_DIR, "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))

# --- 7. ROUTES & LOGIC ---
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None, message: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error, "message": message})

@app.post("/login")
async def handle_login(
    request: Request, 
    email: str = Form(...), 
    password: str = Form(...), 
    db: AsyncSession = Depends(get_db)
):
    email_clean = email.strip().lower()
    result = await db.execute(select(User).where(User.email == email_clean))
    user = result.scalars().first()
    
    if user and pwd_context.verify(password, user.hashed_password):
        if not user.is_verified:
            return templates.TemplateResponse("login.html", {"request": request, "error": "Verify email first."})
        request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials."})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login")
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
    # Use environment port for Railway/Heroku
    port = int(os.environ.get("PORT", 8080))
    # Note: Use string import "app.main:app" to prevent importlib issues
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
