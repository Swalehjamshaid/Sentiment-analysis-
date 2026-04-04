import sys
import os
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Optional, Tuple

from fastapi import FastAPI, Request, Depends, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

# --- 1. SYSTEM PATH ALIGNMENT ---
# In Docker/Railway, we must ensure the parent directory is in sys.path 
# to resolve 'app.core' and 'app.routes' without frozen import errors.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Core internal imports
from app.core.config import settings
from app.core.db import init_models, get_db, SessionLocal, engine
from app.core import models
from app.core.models import User, SCHEMA_VERSION, Config as ConfigModel

# Router imports
from app.routes import auth, companies, dashboard, reviews, exports, google_check

# --- 2. LOGGING & SECURITY ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- 3. STEGMAN SCHEMA HELPERS ---
async def _get_stored_schema_version(session: AsyncSession) -> Optional[str]:
    """Retrieves the SCHEMA_VERSION key from the database config table."""
    try:
        res = await session.execute(
            select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION")
        )
        row = res.scalar_one_or_none()
        return row.value if row else None
    except Exception:
        return None

async def _update_stored_schema_version(session: AsyncSession, version: str):
    """Updates or inserts the current SCHEMA_VERSION into the database."""
    res = await session.execute(
        select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION")
    )
    row = res.scalar_one_or_none()
    if row:
        row.value = version
    else:
        session.add(ConfigModel(key="SCHEMA_VERSION", value=version))
    await session.commit()

# --- 4. LIFESPAN (EVENT LOOP MANAGER) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown. 
    Synchronizes the database schema using the Stegman Rules.
    """
    logger.info("🚀 Review Intel AI: Starting Application Startup...")
    try:
        # Step 1: Ensure initial table structure exists
        await init_models()
        
        # Step 2: Check for version mismatch to trigger auto-reset
        async with SessionLocal() as session:
            old_version = await _get_stored_schema_version(session)
            new_version = str(SCHEMA_VERSION)
            
            if old_version != new_version:
                logger.warning(f"🧩 SCHEMA MISMATCH: DB({old_version}) -> CODE({new_version})")
                logger.warning("🧨 Triggering full database reset (Stegman Rule)...")
                
                async with engine.begin() as conn:
                    # Circular reference safety: models.Base is used here inside the loop
                    await conn.run_sync(models.Base.metadata.drop_all)
                    await conn.run_sync(models.Base.metadata.create_all)
                
                await _update_stored_schema_version(session, new_version)
                logger.info(f"🧱 Database reset complete. Version set to {new_version}")
            else:
                logger.info(f"✅ SCHEMA_VERSION verified: {new_version}")
                
        app.state.schema_version = new_version
        logger.info("🚀 Review Intel AI: Startup Sequence Complete.")
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR DURING STARTUP: {e}")
    
    yield
    logger.info("🛑 Review Intel AI: Application Shutdown Started...")

# --- 5. APP INITIALIZATION ---
app = FastAPI(
    title=getattr(settings, "APP_NAME", "Review SaaS AI"),
    lifespan=lifespan,
)

# --- 6. MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
)

# --- 7. STATIC & TEMPLATE RESOLUTION ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(CURRENT_DIR, "static")
template_dir = os.path.join(CURRENT_DIR, "templates")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=template_dir)

# --- 8. AUTH HELPERS & VIEWS ---
def get_current_user(request: Request):
    return request.session.get("user")

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if get_current_user(request):
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None, message: Optional[str] = None):
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
    """Handles secure user login with verification status check."""
    email_clean = email.strip().lower()
    
    # Query user from DB
    result = await db.execute(select(User).where(User.email == email_clean))
    user = result.scalars().first()
    
    # Validate password and verification status
    if user and pwd_context.verify(password, user.hashed_password):
        if not user.is_verified:
            return templates.TemplateResponse("login.html", {
                "request": request,
                "error": "Account not verified. Please check your email for the link."
            })
            
        # Establish Session
        request.session["user"] = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role
        }
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse("login.html", {
        "request": request, 
        "error": "Invalid email or password."
    })

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
        
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "schema_version": getattr(app.state, "schema_version", SCHEMA_VERSION)
    })

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# --- 9. ROUTER MOUNTING ---
logger.info("🔗 Mounting all API routers...")

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])
app.include_router(exports.router, prefix="/api", tags=["exports"])
app.include_router(google_check.router, prefix="/api", tags=["google_check"])

logger.info("✅ All routers mounted correctly")

# --- 10. RUNNER ---
if __name__ == "__main__":
    import uvicorn
    # Use Railway/Docker PORT or default to 8080
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=port, 
        reload=False
    )
