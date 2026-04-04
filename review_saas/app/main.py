# filename: app/main.py
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
from sqlalchemy.ext.asyncio import AsyncSession

# --- 1. Path Fix for Railway ---
# This ensures that 'import app.core' works regardless of where the command is run.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# --- 2. Core Imports ---
from app.core.config import settings
from app.core.db import init_models, get_db, SessionLocal, engine
from app.core import models
from app.core.models import User, SCHEMA_VERSION, Config as ConfigModel

# --- 3. Router Imports ---
from app.routes import auth, companies, dashboard, reviews, exports, google_check

# --- 4. Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

# --- 5. Stegman Schema Helpers ---
async def _get_stored_schema_version(session: AsyncSession) -> Optional[str]:
    res = await session.execute(
        select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION")
    )
    row = res.scalar_one_or_none()
    return row.value if row else None

async def _set_stored_schema_version(session: AsyncSession, new_value: str) -> None:
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
    async with SessionLocal() as session:
        old_version = await _get_stored_schema_version(session)
        new_version = str(SCHEMA_VERSION)
        if old_version is None:
            await _set_stored_schema_version(session, new_version)
            logger.info("📦 Initialized SCHEMA_VERSION: %s", new_version)
            return False, None, new_version
        if old_version != new_version:
            logger.warning("🧩 SCHEMA changed: %s → %s", old_version, new_version)
            return True, old_version, new_version
        logger.info("✅ SCHEMA_VERSION verified: %s", new_version)
        return False, old_version, new_version

async def reset_database_schema():
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)
        logger.warning("🧨 Dropped all tables")
        await conn.run_sync(models.Base.metadata.create_all)
        logger.info("🧱 Recreated all tables")

# --- 6. Lifespan Event Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Application Startup Started...")
    try:
        # Initialize DB Tables
        await init_models()
        # Handle Stegman Versioning Logic
        changed, old_v, new_v = await check_schema_version_change()
        if changed:
            await reset_database_schema()
            async with SessionLocal() as session:
                await _set_stored_schema_version(session, new_v)
        app.state.schema_version = new_v
        logger.info("🚀 Application Startup Complete")
    except Exception as e:
        logger.error(f"❌ Error during startup: {e}")
    yield
    logger.info("🛑 Application Shutdown Started...")

# --- 7. FastAPI App Initialization ---
app = FastAPI(
    title=getattr(settings, "APP_NAME", "Review SaaS AI"),
    lifespan=lifespan,
)

# --- 8. Middleware ---
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

# --- 9. Static & Template Resolution ---
current_file_dir = os.path.dirname(os.path.abspath(__file__))
static_path = os.path.join(current_file_dir, "static")
template_path = os.path.join(current_file_dir, "templates")

if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

templates = Jinja2Templates(directory=template_path)

# --- 10. Auth Helpers & Base Views ---
def get_current_user(request: Request):
    return request.session.get("user")

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if get_current_user(request):
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(select(User).where(User.email == email.strip().lower()))
    user = result.scalars().first()
    if not user or password != user.hashed_password:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid credentials"}
        )
    request.session["user"] = {
        "id": user.id,
        "email": user.email,
        "name": user.name,
    }
    return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)

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
            "schema_version": getattr(app.state, "schema_version", ""),
        },
    )

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# --- 11. Router Mounting ---
logger.info("🔗 Mounting all routers...")
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])
app.include_router(exports.router, prefix="/api", tags=["exports"])
app.include_router(google_check.router, prefix="/api", tags=["google_check"])
logger.info("✅ All routers mounted correctly")

# --- 12. Execution (Local) ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
