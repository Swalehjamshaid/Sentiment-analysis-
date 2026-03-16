# filename: app/main.py

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Optional, Tuple

import httpx
from fastapi import FastAPI, Request, Depends, Form, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import init_models, get_session, SessionLocal, engine  # add engine for drop/create
from app.core import models  # import models to access Base metadata
from app.core.models import User, SCHEMA_VERSION, Config as ConfigModel

from app.services.review import ingest_outscraper_reviews  # safe import for future use

# ---------------------------
# Logging Setup
# ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

# ---------------------------
# Templates / Static
# ---------------------------
app = FastAPI(title=getattr(settings, "APP_NAME", "ReviewSaaS API"))

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# ---------------------------
# CORS / Session Middleware
# ---------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_secret_key = (
    getattr(settings, "SECRET_KEY", None)
    or os.getenv("SECRET_KEY")
    or "dev-insecure-secret"
)
app.add_middleware(SessionMiddleware, secret_key=_secret_key)

# ---------------------------
# Auth Helpers
# ---------------------------
def get_current_user(request: Request) -> Optional[dict]:
    user = request.session.get("user")
    if user is None:
        return None
    return user

def require_login(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=303, detail="Redirect to login", headers={"Location": "/login"})
    return user

# ---------------------------
# Lifespan & Schema Version
# ---------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_models()
        logger.info("✅ Database schema initialized")
    except Exception as e:
        logger.error("❌ Database startup failed: %s", e)

    # Schema version check
    async with SessionLocal() as session:
        res = await session.execute(select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION"))
        row = res.scalar_one_or_none()
        if row is None or row.value != str(SCHEMA_VERSION):
            # Drop & recreate if changed
            await engine.begin().run_sync(models.Base.metadata.drop_all)
            await engine.begin().run_sync(models.Base.metadata.create_all)
            logger.warning("⚠️ Schema reset due to version change")
            if row:
                row.value = str(SCHEMA_VERSION)
            else:
                session.add(ConfigModel(key="SCHEMA_VERSION", value=str(SCHEMA_VERSION)))
            await session.commit()

    yield  # app ready

app.router.lifespan_context = lifespan

# ---------------------------
# Views / Routes
# ---------------------------
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
    if not user or not getattr(user, "check_password", lambda *_: False)(password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})
    request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "user": None})


@app.post("/register")
async def register_post(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    session_db: AsyncSession = Depends(get_session),
):
    result = await session_db.execute(select(User).where(User.email == email))
    existing = result.scalars().first()
    if existing:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Email already registered"})
    user = User(name=name, email=email)
    if hasattr(user, "set_password"):
        user.set_password(password)
    else:
        user.hashed_password = password  # dev only
    session_db.add(user)
    await session_db.commit()
    await session_db.refresh(user)
    request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: dict = Depends(require_login)):
    google_api_key = (
        getattr(settings, "GOOGLE_API_KEY", None)
        or os.getenv("GOOGLE_API_KEY")
        or ""
    )
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "google_api_key": google_api_key,
        },
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# ---------------------------
# Health Check
# ---------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}

# ---------------------------
# Include Routers Safely
# ---------------------------
def _include_router_safe(module_path: str, attr: str = "router") -> None:
    try:
        mod = __import__(module_path, fromlist=[attr])
        router = getattr(mod, attr, None)
        if router:
            app.include_router(router)
            logger.info("🔗 Included router: %s.%s", module_path, attr)
        else:
            logger.warning("Router attribute '%s' not found in %s", attr, module_path)
    except Exception as e:
        logger.warning("Skipping router %s due to import error: %s", module_path, e)

_include_router_safe("app.routes.auth")
_include_router_safe("app.routes.companies")
_include_router_safe("app.routes.dashboard")
_include_router_safe("app.routes.reviews")  # make sure reviews.py has `router = APIRouter(...)`
_include_router_safe("app.routes.exports")
_include_router_safe("app.routes.google_check")

# ---------------------------
# Run App
# ---------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
