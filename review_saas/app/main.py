import sys
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional, Tuple

from fastapi import FastAPI, Request, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Fix for Docker / Gunicorn import issues
sys.path.insert(0, "/app")

# Core imports
from app.core.config import settings
from app.core.db import init_models, get_session, SessionLocal, engine
from app.core import models
from app.core.models import User, SCHEMA_VERSION, Config as ConfigModel

# Routers
from app.routes import auth, companies, dashboard, reviews, exports, google_check

# --------------------------- Logging ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

# --------------------------- Schema Helpers ---------------------------
async def _get_stored_schema_version(session: AsyncSession) -> Optional[str]:
    res = await session.execute(select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION"))
    row = res.scalar_one_or_none()
    return row.value if row else None

async def _set_stored_schema_version(session: AsyncSession, new_value: str) -> None:
    res = await session.execute(select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION"))
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

# --------------------------- Lifespan ---------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Application Startup Started...")
    try:
        await init_models()
        changed, old_v, new_v = await check_schema_version_change()
        if changed:
            await reset_database_schema()
            async with SessionLocal() as session:
                await _set_stored_schema_version(session, new_v)
        app.state.schema_version = new_v
        logger.info("✅ SCHEMA_VERSION verified: %s", new_v)
        logger.info("🚀 Application Startup Complete")
    except Exception as e:
        logger.error(f"❌ Error during startup: {e}")
    yield
    logger.info("🛑 Application Shutdown Started...")

# --------------------------- App Init ---------------------------
app = FastAPI(
    title=getattr(settings, "APP_NAME", "Review SaaS AI"),
    lifespan=lifespan,
)

# --------------------------- Middleware ---------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "super-secret-key"),
)

# --------------------------- Static & Templates ---------------------------
if os.path.exists("app/static"):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

# --------------------------- Auth Helper ---------------------------
def get_current_user(request: Request):
    return request.session.get("user")

# --------------------------- Views ---------------------------
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if get_current_user(request):
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    # FIXED: Added request=request to fix unhashable type error
    return templates.TemplateResponse(
        request=request, 
        name="login.html", 
        context={"email_hint": "roy.jamshaid@gmail.com"}
    )

@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    # Search for Jamshaid's email
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    
    # Check credentials
    if not user or password != user.hashed_password:
        return templates.TemplateResponse(
            request=request, 
            name="login.html", 
            context={"request": request, "error": "Invalid credentials", "email": email}
        )
    
    request.session["user"] = {
        "id": user.id,
        "email": user.email,
        "name": user.name,
    }
    return RedirectResponse("/dashboard", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    
    # FIXED: Explicit request and context for Jinja2
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "schema_version": getattr(app.state, "schema_version", ""),
        }
    )

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# --------------------------- Routers ---------------------------
logger.info("🔗 Mounting all routers...")
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])
app.include_router(exports.router, prefix="/api", tags=["exports"])
app.include_router(google_check.router, prefix="/api", tags=["google_check"])
logger.info("🔗 All routers mounted correctly")

# --------------------------- Run ---------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
