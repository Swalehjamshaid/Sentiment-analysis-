from __future__ import annotations

import logging
import os
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

# Core imports for Database and Settings
from app.core.config import settings
from app.core.db import init_models, get_session, SessionLocal, engine
from app.core import models
from app.core.models import User, SCHEMA_VERSION, Config as ConfigModel

# Route Imports (Removed ai_insights)
from app.routes import auth, companies, dashboard, reviews, exports, google_check

# --------------------------- Logging Configuration ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

# --------------------------- Database Schema Helpers ---------------------------
async def _get_stored_schema_version(session: AsyncSession) -> Optional[str]:
    try:
        res = await session.execute(select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION"))
        row = res.scalar_one_or_none()
        return row.value if row else None
    except Exception:
        return None

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
            logger.info("📦 Initialized SCHEMA_VERSION in DB: %s", new_version)
            return False, None, new_version
        if old_version != new_version:
            logger.warning("🧩 SCHEMA_VERSION changed: %s -> %s", old_version, new_version)
            return True, old_version, new_version
        logger.info("✅ SCHEMA_VERSION verified: %s", new_version)
        return False, old_version, new_version

async def reset_database_schema() -> None:
    try:
        async with engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.drop_all)
            logger.warning("🧨 Dropped all tables due to version mismatch.")
            await conn.run_sync(models.Base.metadata.create_all)
            logger.info("🧱 Recreated all tables successfully.")
    except Exception as ex:
        logger.error("Schema reset failed: %s", ex, exc_info=True)
        raise

# --------------------------- Application Lifespan ---------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()
    changed, old_v, new_v = await check_schema_version_change()
    if changed:
        await reset_database_schema()
        async with SessionLocal() as session:
            await _set_stored_schema_version(session, new_v)
        logger.warning("⚠️ Database reset complete (%s -> %s).", old_v, new_v)

    app.state.schema_version = new_v
    app.state.schema_changed = changed
    app.state.schema_prev = old_v

    logger.info("🚀 Application Startup Sequence Complete")
    yield

# --------------------------- App Initialization ---------------------------
app = FastAPI(
    title=getattr(settings, "APP_NAME", "ReviewSaaS AI Dashboard"), 
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_secret_key = os.getenv("SECRET_KEY") or getattr(settings, "SECRET_KEY", "dev-insecure-secret-key-999")
app.add_middleware(SessionMiddleware, secret_key=_secret_key)

if os.path.exists("app/static"):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

# --------------------------- Auth Helpers ---------------------------
def get_current_user(request: Request) -> Optional[dict]:
    return request.session.get("user")

# --------------------------- View Routes (HTML) ---------------------------
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/login")

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "user": None})

@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session_db: AsyncSession = Depends(get_session),
):
    result = await session_db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    
    if not user or not getattr(user, "check_password", lambda p: p == user.hashed_password)(password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid email or password"})
    
    request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    google_api_key = os.getenv("GOOGLE_API_KEY") or getattr(settings, "GOOGLE_API_KEY", "")
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "google_api_key": google_api_key,
            "schema_version": getattr(app.state, "schema_version", "22.0.5"),
        },
    )

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

# --------------------------- API Router Registration ---------------------------
app.include_router(auth.router, prefix="/api/auth")
app.include_router(companies.router, prefix="/api/companies")
app.include_router(dashboard.router, prefix="/api/dashboard")
app.include_router(reviews.router, prefix="/api/reviews")
# Router for ai_insights HAS BEEN REMOVED
app.include_router(exports.router, prefix="/api/exports")
app.include_router(google_check.router, prefix="/api/google_check")

logger.info("🔗 Routers Mounted: Auth, Companies, Dashboard, Reviews, Exports, GoogleCheck")

# --------------------------- Server Execution ---------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
