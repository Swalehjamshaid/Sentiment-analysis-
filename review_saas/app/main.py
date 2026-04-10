# filename: app/main.py
import os
import sys
import logging
import traceback
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from sqlalchemy.ext.asyncio import AsyncSession

from passlib.context import CryptContext
from loguru import logger

# ----------------------------------------------------------
# CORE IMPORTS
# ----------------------------------------------------------
from app.core.config import settings
from app.core.db import init_models, get_db

# ----------------------------------------------------------
# LOGGING
# ----------------------------------------------------------
logger.remove()
logger.add(sys.stdout, level="DEBUG", backtrace=True, diagnose=True, enqueue=True)
logging.basicConfig(level=logging.INFO)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ----------------------------------------------------------
# LIFESPAN
# ----------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Review Intel AI...")
    try:
        await init_models()
        logger.info("✅ Database initialized successfully")
    except Exception:
        logger.error("❌ Database initialization failed")
        logger.error(traceback.format_exc())
    yield
    logger.info("🛑 Application shutdown complete")


# ----------------------------------------------------------
# APP INIT
# ----------------------------------------------------------
app = FastAPI(title="Review Intel AI", lifespan=lifespan)

# ----------------------------------------------------------
# GLOBAL ERROR HANDLER
# ----------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"❌ GLOBAL ERROR at {request.url}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error", "detail": str(exc)},
    )


# ----------------------------------------------------------
# MIDDLEWARE
# ----------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# ----------------------------------------------------------
# TEMPLATES
# ----------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
possible_paths = [
    os.path.join(BASE_DIR, "templates"),
    "/app/app/templates",
    "/app/templates",
]
template_path = next((p for p in possible_paths if os.path.isdir(p)), None)
if not template_path:
    raise RuntimeError("❌ Templates directory NOT FOUND")

templates = Jinja2Templates(directory=template_path)
templates.env.cache = None
logger.info(f"✅ Templates loaded from: {template_path}")

# ----------------------------------------------------------
# JINJA FILTER
# ----------------------------------------------------------
def format_date(value, format="%Y-%m-%d"):
    if not value:
        return ""
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        return value.strftime(format)
    except Exception:
        return str(value)

templates.env.filters["date"] = format_date

# ----------------------------------------------------------
# STATIC FILES
# ----------------------------------------------------------
static_paths = [os.path.join(BASE_DIR, "static"), "/app/app/static", "/app/static"]
static_dir = next((p for p in static_paths if os.path.isdir(p)), None)
if static_dir:
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"📁 Static files mounted from: {static_dir}")

# ----------------------------------------------------------
# ROUTES IMPORT
# ----------------------------------------------------------
from app.routes import auth, companies, dashboard, reviews

# ----------------------------------------------------------
# UI ROUTES
# ----------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")


@app.post("/login")
async def handle_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    from app.core.models import User
    try:
        result = await db.execute(
            select(User).where(User.email == email.strip().lower())
        )
        user = result.scalars().first()

        if user and pwd_context.verify(password, user.hashed_password):
            request.session["user"] = {
                "id": user.id,
                "email": user.email,
                "name": user.name,
            }
            return RedirectResponse("/dashboard", status_code=303)

        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Invalid email or password"}
        )
    except Exception:
        logger.error("❌ Login Error")
        logger.error(traceback.format_exc())
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Something went wrong. Please try again."}
        )


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"user": request.session.get("user")}
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ----------------------------------------------------------
# API ROUTES
# ----------------------------------------------------------
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])


# ----------------------------------------------------------
# ENTRYPOINT
# ----------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
