# filename: app/main.py
import sys
import os
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Depends, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

# ---------------------------------------------------------
# 1. SYSTEM PATH ALIGNMENT
# ---------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ---------------------------------------------------------
# 2. LOGGING (Before Sentry)
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

# ---------------------------------------------------------
# 3. CORE IMPORTS
# ---------------------------------------------------------
try:
    from app.core.config import settings
    from app.core.db import init_models, get_db, SessionLocal, engine
    from app.core import models
    from app.core.models import User, SCHEMA_VERSION, Config as ConfigModel
    logger.info("✅ Core modules imported")
except Exception as e:
    logger.error("❌ Failed to import core modules", exc_info=True)
    raise

# Safe router imports
try:
    from app.routes import auth, companies, dashboard, reviews, exports, google_check
    logger.info("✅ All routers imported successfully")
except Exception as e:
    logger.error("❌ Failed to import routers", exc_info=True)
    auth = companies = dashboard = reviews = exports = google_check = None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------
# 4. SCHEMA VERSION HELPERS
# ---------------------------------------------------------
async def _get_stored_schema_version(session: AsyncSession) -> Optional[str]:
    try:
        res = await session.execute(
            select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION")
        )
        row = res.scalar_one_or_none()
        return row.value if row else None
    except Exception as e:
        logger.error("Failed to read SCHEMA_VERSION from database", exc_info=True)
        raise

async def _update_stored_schema_version(session: AsyncSession, version: str):
    try:
        res = await session.execute(
            select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION")
        )
        row = res.scalar_one_or_none()
        if row:
            row.value = version
        else:
            session.add(ConfigModel(key="SCHEMA_VERSION", value=version))
        await session.commit()
    except Exception as e:
        logger.error("Failed to update SCHEMA_VERSION", exc_info=True)
        raise

# ---------------------------------------------------------
# 5. LIFESPAN (With Sentry initialization here)
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Sentry INSIDE lifespan, not at module level
    import sentry_sdk
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    
    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[
                AsyncioIntegration(),
                FastApiIntegration(),
                LoggingIntegration(
                    level=logging.INFO,
                    event_level=logging.ERROR,
                ),
            ],
            traces_sample_rate=0.2,
            environment=os.getenv("ENVIRONMENT", "production"),
        )
        logger.info("✅ Sentry SDK initialized successfully")
    else:
        logger.warning("⚠️ SENTRY_DSN not set - Sentry disabled")
    
    logger.info("🚀 Review Intel AI: Starting application startup")
    
    try:
        # Initialize database
        await init_models()
        
        async with SessionLocal() as session:
            old_version = await _get_stored_schema_version(session)
            new_version = str(SCHEMA_VERSION)
            
            if old_version != new_version:
                logger.warning(f"🧩 SCHEMA MISMATCH: DB({old_version}) -> CODE({new_version})")
                logger.warning("🧨 Performing full schema reset")
                async with engine.begin() as conn:
                    await conn.run_sync(models.Base.metadata.drop_all)
                    await conn.run_sync(models.Base.metadata.create_all)
                await _update_stored_schema_version(session, new_version)
                logger.info(f"🧱 Database reset complete. Version={new_version}")
            else:
                logger.info(f"✅ SCHEMA_VERSION verified: {new_version}")
        
        app.state.schema_version = new_version
        logger.info("✅ Startup sequence completed successfully")
        
    except Exception as e:
        logger.error("❌ CRITICAL ERROR DURING APPLICATION STARTUP", exc_info=True)
        # Report to Sentry if available
        if sentry_dsn:
            sentry_sdk.capture_exception(e)
        raise
    
    yield
    
    logger.info("🛑 Application shutdown initiated")
    
    # Cleanup Sentry
    if sentry_dsn:
        sentry_sdk.flush()

# ---------------------------------------------------------
# 6. FASTAPI + MIDDLEWARE + TEMPLATES
# ---------------------------------------------------------
app = FastAPI(
    title=getattr(settings, "APP_NAME", "Review SaaS AI"),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# Ensure SECRET_KEY is set
if not hasattr(settings, 'SECRET_KEY') or not settings.SECRET_KEY:
    logger.error("❌ SECRET_KEY not configured in settings!")
    raise RuntimeError("SECRET_KEY is required for SessionMiddleware")

app.add_middleware(
    SessionMiddleware, 
    secret_key=settings.SECRET_KEY
)

# Better template/static path handling
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(CURRENT_DIR, "static")
template_dir = os.path.join(CURRENT_DIR, "templates")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"✅ Static mounted from {static_dir}")
else:
    logger.warning(f"⚠️ Static dir not found: {static_dir}")

# Only initialize templates if directory exists
if os.path.exists(template_dir):
    templates = Jinja2Templates(directory=template_dir)
    logger.info(f"✅ Templates loaded from {template_dir}")
else:
    logger.error(f"❌ Templates directory not found: {template_dir}")
    raise RuntimeError(f"Templates directory missing: {template_dir}")

# ---------------------------------------------------------
# 7. AUTH HELPERS & VIEWS
# ---------------------------------------------------------
def get_current_user(request: Request):
    return request.session.get("user")

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if get_current_user(request):
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    error: Optional[str] = None,
    message: Optional[str] = None,
):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": error, "message": message},
    )

@app.post("/login")
async def handle_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    email_clean = email.strip().lower()
    
    result = await db.execute(select(User).where(User.email == email_clean))
    user = result.scalars().first()
    
    if user and pwd_context.verify(password, user.hashed_password):
        if not user.is_verified:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "Account not verified. Please check your email.",
                },
            )
        
        request.session["user"] = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
        }
        return RedirectResponse(
            "/dashboard", status_code=status.HTTP_303_SEE_OTHER
        )
    
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Invalid email or password."},
    )

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "schema_version": getattr(app.state, "schema_version", SCHEMA_VERSION),
        },
    )

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# ---------------------------------------------------------
# 8. ROUTER MOUNTING
# ---------------------------------------------------------
logger.info("🔗 Mounting API routers")
routers_mounted = 0

for router_name, router in [
    ("auth", auth), 
    ("companies", companies), 
    ("dashboard", dashboard),
    ("reviews", reviews), 
    ("exports", exports), 
    ("google_check", google_check)
]:
    if router and hasattr(router, "router"):
        try:
            prefix = "/api/auth" if router_name == "auth" else "/api"
            app.include_router(router.router, prefix=prefix, tags=[router_name])
            logger.info(f"✅ Mounted router: {router_name}")
            routers_mounted += 1
        except Exception as e:
            logger.error(f"❌ Failed to mount router {router_name}", exc_info=True)

logger.info(f"✅ {routers_mounted}/6 routers mounted successfully")

# ---------------------------------------------------------
# 9. LOCAL RUNNER
# ---------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )
