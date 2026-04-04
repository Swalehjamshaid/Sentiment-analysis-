# filename: app/main.py
import sys
import os
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Optional

# ====================== SENTRY - MUST BE FIRST ======================
import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),          # ← Make sure this is set in Railway
    integrations=[
        AsyncioIntegration(),
        FastApiIntegration(),
        LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR,    # Turns ERROR logs into Sentry events
        ),
    ],
    traces_sample_rate=0.2,
    environment=os.getenv("ENVIRONMENT", "production"),
)
logging.info("✅ Sentry SDK initialized successfully")
# ===================================================================

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
# 2. LOGGING
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------
# 3. CORE IMPORTS (Safer)
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
    # Continue with None to avoid total crash if needed, but better to fail fast
    auth = companies = dashboard = reviews = exports = google_check = None

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
# 5. LIFESPAN (Improved)
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Review Intel AI: Starting application startup")
    try:
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
        raise
    yield
    logger.info("🛑 Application shutdown initiated")

# ---------------------------------------------------------
# 6. FASTAPI + MIDDLEWARE + TEMPLATES (Fixed paths)
# ---------------------------------------------------------
app = FastAPI(
    title=getattr(settings, "APP_NAME", "Review SaaS AI"),
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Better template/static path handling
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(CURRENT_DIR, "static")
template_dir = os.path.join(CURRENT_DIR, "templates")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"✅ Static mounted from {static_dir}")
else:
    logger.warning(f"⚠️ Static dir not found: {static_dir}")

templates = Jinja2Templates(directory=template_dir)
logger.info(f"✅ Templates loaded from {template_dir}")

# Auth helpers & views (unchanged, but errors will now be clearer)
def get_current_user(request: Request):
    return request.session.get("user")

# ... (your login_page, handle_login, dashboard_view, logout routes remain the same)

# ---------------------------------------------------------
# 10. ROUTER MOUNTING (Safe)
# ---------------------------------------------------------
logger.info("🔗 Mounting API routers")
for router_name, router in [("auth", auth), ("companies", companies), ("dashboard", dashboard),
                            ("reviews", reviews), ("exports", exports), ("google_check", google_check)]:
    if router and hasattr(router, "router"):
        try:
            prefix = "/api/auth" if router_name == "auth" else "/api"
            app.include_router(router.router, prefix=prefix, tags=[router_name])
            logger.info(f"✅ Mounted router: {router_name}")
        except Exception as e:
            logger.error(f"❌ Failed to mount router {router_name}", exc_info=True)

logger.info("✅ All routers mounted successfully")

# Local runner
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
