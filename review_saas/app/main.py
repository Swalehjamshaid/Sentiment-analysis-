# filename: app/main.py

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
    await init_models()

    changed, old_v, new_v = await check_schema_version_change()

    if changed:
        await reset_database_schema()
        async with SessionLocal() as session:
            await _set_stored_schema_version(session, new_v)

    app.state.schema_version = new_v

    logger.info("🚀 Application Startup Complete")
    yield

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
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(User).where(User.email == email))
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

    return RedirectResponse("/dashboard", status_code=303)

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

# --------------------------- ROUTERS (FIXED) ---------------------------

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
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
