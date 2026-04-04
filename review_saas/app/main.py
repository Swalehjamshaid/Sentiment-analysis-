# filename: app/main.py
import sys
import os
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

# --- 1. PATH RESOLUTION (Strict Alignment) ---
# This ensures the 'app' package is discoverable from the project root
CURRENT_FILE_PATH = os.path.abspath(__file__)
APP_DIR = os.path.dirname(CURRENT_FILE_PATH)
ROOT_DIR = os.path.dirname(APP_DIR)

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Core internal imports - Level 1 & 2
try:
    from app.core.config import settings
    from app.core.db import init_models, get_db, SessionLocal, engine
    from app.core import models
    from app.core.models import User, SCHEMA_VERSION, Config as ConfigModel
    
    # Router imports - Level 4
    from app.routes import auth, companies, dashboard, reviews, exports, google_check
except ImportError as e:
    print(f"CRITICAL ALIGNMENT ERROR: {e}")
    raise

# --- 2. LOGGING & SECURITY ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- 3. DATABASE HELPERS (Schema Versioning) ---
async def _get_stored_schema_version(session: AsyncSession) -> Optional[str]:
    """Retrieves the current schema version from the DB."""
    try:
        res = await session.execute(
            select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION")
        )
        row = res.scalar_one_or_none()
        return row.value if row else None
    except Exception:
        return None

async def _update_stored_schema_version(session: AsyncSession, version: str):
    """Updates the database with the current code's schema version."""
    res = await session.execute(
        select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION")
    )
    row = res.scalar_one_or_none()
    if row:
        row.value = version
    else:
        session.add(ConfigModel(key="SCHEMA_VERSION", value=version))
    await session.commit()

# --- 4. LIFESPAN (Application Startup/Shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles initialization. Using the lifespan ensures that database
    checks happen AFTER the module import phase to prevent exec_module crashes.
    """
    logger.info("🚀 Starting Review Intel AI...")
    try:
        # Step 1: Initialize DB tables if they don't exist
        await init_models()
        
        # Step 2: Handle Schema Transitions
        async with SessionLocal() as session:
            old_v = await _get_stored_schema_version(session)
            new_v = str(SCHEMA_VERSION)
            
            if old_v != new_v:
                logger.warning(f"🧩 Schema Mismatch: {old_v} -> {new_v}. Resetting...")
                async with engine.begin() as conn:
                    # Uses the aligned models metadata from Level 2
                    await conn.run_sync(models.Base.metadata.drop_all)
                    await conn.run_sync(models.Base.metadata.create_all)
                await _update_stored_schema_version(session, new_v)
            else:
                logger.info(f"✅ Schema verified: {new_v}")
        
        # Store version in app state for UI access
        app.state.schema_version = new_v
        
    except Exception as e:
        logger.error(f"❌ Lifespan Startup Error: {str(e)}")
        
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

# Important: Using the SECRET_KEY from Level 1 Configuration
app.add_middleware(
    SessionMiddleware, 
    secret_key=getattr(settings, "SECRET_KEY", "fallback-dev-key-2026")
)

# --- 6. STATIC & TEMPLATES (Dynamic Path Alignment) ---
static_dir = os.path.join(APP_DIR, "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))

# --- 7. GLOBAL ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None, message: str = None):
    return templates.TemplateResponse("login.html", {
        "request": request, 
        "error": error, 
        "message": message
    })

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
            return templates.TemplateResponse("login.html", {
                "request": request, 
                "error": "Please verify your email first."
            })
        
        # Store user info in session
        request.session["user"] = {
            "id": user.id, 
            "email": user.email, 
            "name": user.name
        }
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse("login.html", {
        "request": request, 
        "error": "Invalid email or password."
    })

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

# --- 8. MOUNT ROUTERS (Level 4 Alignment) ---
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])
app.include_router(exports.router, prefix="/api", tags=["exports"])
app.include_router(google_check.router, prefix="/api", tags=["google_check"])

# --- 9. PRODUCTION ENTRYPOINT ---
if __name__ == "__main__":
    import uvicorn
    # Respect Railway/Docker PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    # Standard: Use string loading to prevent double-import cycles
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
