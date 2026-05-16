# ==========================================================
# FILE: app/main.py
# ==========================================================

import os
import sys
import traceback
import logging

from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    Request,
)

from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    JSONResponse,
)

from fastapi.middleware.cors import CORSMiddleware

from starlette.middleware.sessions import (
    SessionMiddleware
)

from starlette.templating import (
    Jinja2Templates
)

from starlette.staticfiles import (
    StaticFiles
)

from loguru import logger

# ==========================================================
# CORE IMPORTS
# ==========================================================

from app.core.config import settings
from app.core.db import init_models

# ==========================================================
# ROUTES IMPORTS
# ==========================================================

from app.routes import auth
from app.routes import companies
from app.routes import dashboard
from app.routes import reviews
from app.routes import chatbot
from app.routes import reports

# ==========================================================
# LOGGING
# ==========================================================

logger.remove()

logger.add(
    sys.stdout,
    level="DEBUG",
    backtrace=True,
    diagnose=True,
    enqueue=True
)

logging.basicConfig(level=logging.INFO)

# ==========================================================
# BASE DIRECTORY
# ==========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

# ==========================================================
# LIFESPAN
# ==========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info(
        "🚀 Starting Review Intel AI"
    )

    try:

        await init_models()

        logger.success(
            "✅ Database initialized successfully"
        )

    except Exception as e:

        logger.error(
            "❌ Database initialization failed"
        )

        logger.error(
            traceback.format_exc()
        )

        raise e

    yield

    logger.info(
        "🛑 Application shutdown complete"
    )

# ==========================================================
# FASTAPI APP
# ==========================================================

app = FastAPI(

    title="Review Intel AI",

    description="""
    AI Reputation Monitoring &
    Business Intelligence Platform
    """,

    version="3.0.0",

    lifespan=lifespan
)

# ==========================================================
# GLOBAL ERROR HANDLER
# ==========================================================

@app.exception_handler(Exception)

async def global_exception_handler(

    request: Request,

    exc: Exception

):

    logger.error(
        f"❌ GLOBAL ERROR: {request.url}"
    )

    logger.error(
        traceback.format_exc()
    )

    return JSONResponse(

        status_code=500,

        content={

            "status":
                "error",

            "message":
                "Internal Server Error",

            "detail":
                str(exc)
        }
    )

# ==========================================================
# CORS
# ==========================================================

app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)

# ==========================================================
# SESSION MIDDLEWARE
# ==========================================================

app.add_middleware(

    SessionMiddleware,

    secret_key=settings.SECRET_KEY,

    session_cookie="review_intel_session",

    max_age=86400,

    same_site="lax",

    https_only=False
)

# ==========================================================
# TEMPLATE DIRECTORY
# ==========================================================

TEMPLATE_DIR = os.path.join(
    BASE_DIR,
    "templates"
)

if not os.path.exists(TEMPLATE_DIR):

    raise RuntimeError(
        f"❌ Templates folder not found: {TEMPLATE_DIR}"
    )

templates = Jinja2Templates(
    directory=TEMPLATE_DIR
)

templates.env.cache = None

logger.success(
    f"✅ Templates Loaded: {TEMPLATE_DIR}"
)

# ==========================================================
# DATE FILTER
# ==========================================================

def format_date(
    value,
    format="%Y-%m-%d"
):

    if not value:
        return ""

    try:

        if isinstance(value, str):

            value = datetime.fromisoformat(
                value
            )

        return value.strftime(format)

    except Exception:

        return str(value)

templates.env.filters["date"] = format_date

# ==========================================================
# STATIC FILES
# ==========================================================

STATIC_DIR = os.path.join(
    BASE_DIR,
    "static"
)

if os.path.exists(STATIC_DIR):

    app.mount(

        "/static",

        StaticFiles(directory=STATIC_DIR),

        name="static"
    )

    logger.success(
        f"✅ Static Mounted: {STATIC_DIR}"
    )

else:

    logger.warning(
        "⚠️ Static folder not found"
    )

# ==========================================================
# ROOT
# ==========================================================

@app.get(
    "/",
    response_class=HTMLResponse
)

async def root(
    request: Request
):

    if not request.session.get("user_id"):

        return RedirectResponse(
            "/login",
            status_code=303
        )

    return RedirectResponse(
        "/dashboard",
        status_code=303
    )

# ==========================================================
# LOGIN PAGE
# ==========================================================

@app.get(
    "/login",
    response_class=HTMLResponse
)

async def login_page(
    request: Request
):

    return templates.TemplateResponse(

        {
            "request": request
        },

        "login.html"
    )

# ==========================================================
# REGISTER PAGE
# ==========================================================

@app.get(
    "/register",
    response_class=HTMLResponse
)

async def register_page(
    request: Request
):

    return templates.TemplateResponse(

        {
            "request": request
        },

        "register.html"
    )

# ==========================================================
# DASHBOARD PAGE
# ==========================================================

@app.get(
    "/dashboard",
    response_class=HTMLResponse
)

async def dashboard_page(
    request: Request
):

    if not request.session.get("user_id"):

        return RedirectResponse(
            "/login",
            status_code=303
        )

    return templates.TemplateResponse(

        {

            "request": request,

            "user": {

                "id":
                    request.session.get(
                        "user_id"
                    ),

                "name":
                    request.session.get(
                        "user_name"
                    ),

                "email":
                    request.session.get(
                        "user_email"
                    )
            }
        },

        "dashboard.html"
    )

# ==========================================================
# LOGOUT
# ==========================================================

@app.get("/logout")
@app.get("/api/auth/logout")

async def logout(
    request: Request
):

    request.session.clear()

    logger.info(
        "✅ User logged out"
    )

    return RedirectResponse(
        "/login",
        status_code=303
    )

# ==========================================================
# HEALTH CHECK
# ==========================================================

@app.get("/health")

async def health_check():

    return {

        "status":
            "healthy",

        "service":
            "Review Intel AI",

        "timestamp":
            datetime.utcnow().isoformat()
    }

# ==========================================================
# INCLUDE ROUTERS
# ==========================================================

app.include_router(

    auth.router,

    prefix="/api/auth",

    tags=["Authentication"]
)

app.include_router(

    companies.router,

    prefix="/api",

    tags=["Companies"]
)

app.include_router(

    dashboard.router,

    prefix="/api",

    tags=["Dashboard"]
)

app.include_router(

    reviews.router,

    prefix="/api",

    tags=["Reviews"]
)

app.include_router(

    chatbot.router,

    prefix="/api",

    tags=["Chatbot"]
)

# ==========================================================
# REPORTS ROUTER
# ==========================================================

app.include_router(
    reports.router
)

logger.success(
    "✅ Reports router enabled"
)

# ==========================================================
# STARTUP
# ==========================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(

        "app.main:app",

        host="0.0.0.0",

        port=int(
            os.environ.get(
                "PORT",
                8080
            )
        ),

        reload=True,

        workers=1
    )
