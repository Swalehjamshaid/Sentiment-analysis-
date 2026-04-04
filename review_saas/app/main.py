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
# 1. SYSTEM PATH ALIGNMENT (CRITICAL FOR DOCKER / GUNICORN)
# ---------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ---------------------------------------------------------
# 2. CORE INTERNAL IMPORTS (SAFE AFTER PATH ALIGNMENT)
# ---------------------------------------------------------
from app.core.config import settings
from app.core.db import init_models, get_db, SessionLocal, engine
from app.core import models
from app.core.models import User, SCHEMA_VERSION, Config as ConfigModel

# Routers
from app.routes import auth, companies, dashboard, reviews, exports, google_check

# ---------------------------------------------------------
# 3. LOGGING CONFIGURATION
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------
# 4. SCHEMA VERSION HELPERS (NO SILENT FAILURES)
# ---------------------------------------------------------
async def _get_stored_schema_version(session: AsyncSession) -> Optional[str]:
    """Retrieve SCHEMA_VERSION from config table."""
    try:
        res = await session.execute(
            select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION")
        )
        row = res.scalar_one_or_none()
        return row.value if row else None
    except Exception:
        logger.exception("Failed to read SCHEMA_VERSION from database")
        raise


async def _update_stored_schema_version(session: AsyncSession, version: str):
    """Insert or update SCHEMA_VERSION in config table."""
    res = await session.execute(
        select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION")
    )
    row = res.scalar_one_or_none()
    if row:
        row.value = version
    else:
        session.add(ConfigModel(key="SCHEMA_VERSION", value=version))
    await session.commit()

# ---------------------------------------------------------
# 5. APPLICATION LIFESPAN (HARD FAIL ON STARTUP ERRORS)
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Review Intel AI: Starting application startup")

    try:
        # Ensure base tables exist
        await init_models()

        async with SessionLocal() as session:
            old_version = await _get_stored_schema_version(session)
            new_version = str(SCHEMA_VERSION)

            if old_version != new_version:
                logger.warning(
                    f"🧩 SCHEMA MISMATCH: DB({old_version}) -> CODE({new_version})"
                )
                logger.warning("🧨 Performing full schema reset (Stegman Rule)")

                async with engine.begin() as conn:
                    await conn.run_sync(models.Base.metadata.drop_all)
                    await conn.run_sync(models.Base.metadata.create_all)

                await _update_stored_schema_version(session, new_version)
                logger.info(f"🧱 Database reset complete. Version={new_version}")
            else:
                logger.info(f"✅ SCHEMA_VERSION verified: {new_version}")

        app.state.schema_version = new_version
        logger.info("✅ Startup sequence completed successfully")

    except Exception:
        # CRITICAL: never swallow startup exceptions
        logger.exception("❌ CRITICAL ERROR DURING APPLICATION STARTUP")
        raise

    yield

    logger.info("🛑 Application shutdown initiated")

# ---------------------------------------------------------
# 6. FASTAPI APPLICATION
# ---------------------------------------------------------
app = FastAPI(
    title=getattr(settings, "APP_NAME", "Review SaaS AI"),
    lifespan=lifespan,
)

# ---------------------------------------------------------
# 7. MIDDLEWARE
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# 8. STATIC FILES & TEMPLATES
# ---------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(CURRENT_DIR, "static")
template_dir = os.path.join(CURRENT_DIR, "templates")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=template_dir)

# ---------------------------------------------------------
# 9. AUTH HELPERS & VIEWS
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
# 10. ROUTER MOUNTING
# ---------------------------------------------------------
logger.info("🔗 Mounting API routers")

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])
app.include_router(exports.router, prefix="/api", tags=["exports"])
app.include_router(google_check.router, prefix="/api", tags=["google_check"])

logger.info("✅ All routers mounted successfully")

# ---------------------------------------------------------
# 11. LOCAL RUNNER (DOCKER / RAILWAY SAFE)
# ---------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
``
