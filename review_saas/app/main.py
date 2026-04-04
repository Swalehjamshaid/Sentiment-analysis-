# filename: app/main.py
import sys
import os
import logging
import secrets
import resend
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from typing import Optional, Tuple, Dict, Any

from fastapi import FastAPI, Request, Depends, Form, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# --- 1. PATH RESOLUTION (Crucial for Docker/Railway) ---
# Ensures the 'app' package is discoverable by the Python interpreter
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# --- 2. CORE IMPORTS ---
from app.core.config import settings
from app.core.db import init_models, get_session, SessionLocal, engine
from app.core import models
from app.core.models import User, SCHEMA_VERSION, Config as ConfigModel

# --- 3. ROUTER IMPORTS ---
from app.routes import auth, companies, dashboard, reviews, exports, google_check

# --- 4. LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

# --- 5. STEGMAN SCHEMA HELPERS ---
async def _get_stored_schema_version(session: AsyncSession) -> Optional[str]:
    """Retrieves the version string from the 'config' table."""
    res = await session.execute(
        select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION")
    )
    row = res.scalar_one_or_none()
    return row.value if row else None

async def _set_stored_schema_version(session: AsyncSession, new_value: str) -> None:
    """Updates or creates the SCHEMA_VERSION in the 'config' table."""
    res = await session.execute(
        select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION")
    )
    row = res.scalar_one_or_none()
    if row:
        row.value = new_value
    else:
        row = ConfigModel(key="SCHEMA_VERSION", value=new_value)
        session.add(row)
    await session.commit()

async def check_schema_version_change() -> Tuple[bool, Optional[str], str]:
    """Compares code-level SCHEMA_VERSION with the database state."""
    async with SessionLocal() as session:
        old_version = await _get_stored_schema_version(session)
        new_version = str(SCHEMA_VERSION)
        
        if old_version is None:
            await _set_stored_schema_version(session, new_version)
            logger.info("📦 Initialized SCHEMA_VERSION: %s", new_version)
            return False, None, new_version
            
        if old_version != new_version:
            logger.warning("🧩 SCHEMA Mismatch: %s -> %s", old_version, new_version)
            return True, old_version, new_version
            
        logger.info("✅ SCHEMA_VERSION verified: %s", new_version)
        return False, old_version, new_version

async def reset_database_schema():
    """Drops all existing tables and recreates them from scratch."""
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)
        logger.warning("🧨 RESET: All tables dropped.")
        await conn.run_sync(models.Base.metadata.create_all)
        logger.info("🧱 RESET: All tables recreated.")

# --- 6. LIFESPAN (App Lifecycle Manager) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Review Intel AI Application...")
    try:
        # Step 1: Ensure initial table creation
        await init_models()
        
        # Step 2: Run Stegman Logic for Version Checks
        changed, old_v, new_v = await check_schema_version_change()
        if changed:
            await reset_database_schema()
            async with SessionLocal() as session:
                await _set_stored_schema_version(session, new_v)
                
        app.state.schema_version = new_v
        logger.info("✅ Application Startup sequence finished.")
    except Exception as e:
        logger.error(f"❌ Critical Error during startup: {e}")
    yield
    logger.info("🛑 Application Shutdown sequence started...")

# --- 7. APP INITIALIZATION ---
app = FastAPI(
    title=getattr(settings, "APP_NAME", "Review SaaS AI"),
    lifespan=lifespan,
)

# --- 8. MIDDLEWARE ---
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

# --- 9. STATIC & TEMPLATE PATH RESOLUTION ---
CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_PATH = os.path.join(CURRENT_FILE_DIR, "static")
TEMPLATE_PATH = os.path.join(CURRENT_FILE_DIR, "templates")

if os.path.exists(STATIC_PATH):
    app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")

templates = Jinja2Templates(directory=TEMPLATE_PATH)

# --- 10. AUTH CONSTANTS & MAGIC LINK LOGIC ---
ADMIN_EMAIL = "roy.jamshaid@gmail.com"
ADMIN_PASSWORD = "Jamshaid,1981"
resend.api_key = os.getenv("RESEND_API_KEY", "re_D8MWpa1c_44ph6mZDfDoCXmEkeoYtPQqC")
MAGIC_TOKENS: Dict[str, Dict[str, Any]] = {}

def get_current_user(request: Request):
    return request.session.get("user")

# --- 11. CORE VIEWS & LOGIN LOGIC ---
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if get_current_user(request):
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request, error: Optional[str] = None, message: Optional[str] = None):
    return templates.TemplateResponse("login.html", {
        "request": request, 
        "error": error, 
        "message": message
    })

@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(None),
    db: AsyncSession = Depends(get_session),
):
    email_clean = email.strip().lower()

    # --- ADMIN BYPASS ---
    if email_clean == ADMIN_EMAIL.lower() and password == ADMIN_PASSWORD:
        request.session["user"] = {"email": email_clean, "role": "admin", "name": "Admin Jamshaid"}
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    # --- MAGIC LINK FLOW ---
    token = secrets.token_urlsafe(32)
    MAGIC_TOKENS[token] = {
        "email": email_clean,
        "expires": datetime.now(timezone.utc) + timedelta(minutes=15)
    }
    
    verify_url = f"{settings.APP_BASE_URL}/verify?token={token}"
    
    try:
        resend.Emails.send({
            "from": "Review Intel AI <onboarding@resend.dev>",
            "to": [email_clean],
            "subject": "Sign in to Review Intel AI",
            "html": f'<p>Click to sign in: <a href="{verify_url}">Login Now</a></p>'
        })
        return templates.TemplateResponse("login.html", {
            "request": request, 
            "message": "✅ Magic link sent! Check your inbox."
        })
    except Exception as e:
        logger.error(f"❌ Resend Failure: {e}")
        return RedirectResponse("/login?error=Failed to send email")

@app.get("/verify")
async def verify_token(request: Request, token: str):
    data = MAGIC_TOKENS.get(token)
    if data and data["expires"] > datetime.now(timezone.utc):
        request.session["user"] = {"email": data["email"], "role": "user"}
        del MAGIC_TOKENS[token]
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login?error=Link expired or invalid")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "schema_version": getattr(app.state, "schema_version", SCHEMA_VERSION),
    })

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# --- 12. ROUTER MOUNTING ---
logger.info("🔗 Mounting API Routers...")
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])
app.include_router(exports.router, prefix="/api", tags=["exports"])
app.include_router(google_check.router, prefix="/api", tags=["google_check"])

# --- 13. SERVER EXECUTION ---
if __name__ == "__main__":
    import uvicorn
    # Use Railway provided PORT
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
