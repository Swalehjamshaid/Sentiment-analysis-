# ==========================================================
# FILE: app/main.py
# TRUSTLYTICS AI — FINAL FULLY INTEGRATED MAIN.PY
# LOGIN + DASHBOARD + ROUTES + TEMPLATES
# MAY 2026 ENTERPRISE VERSION
# ==========================================================

import os
import sys
import traceback
import logging

from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    Request
)

from fastapi.responses import (
    JSONResponse,
    HTMLResponse,
    RedirectResponse
)

from fastapi.middleware.cors import (
    CORSMiddleware
)

from starlette.middleware.sessions import (
    SessionMiddleware
)

from starlette.staticfiles import (
    StaticFiles
)

from starlette.templating import (
    Jinja2Templates
)

from loguru import logger

# ==========================================================
# STARTUP INFO
# ==========================================================

print("🚀 TRUSTLYTICS AI STARTING")

print(
    f"🐍 PYTHON VERSION: {sys.version}"
)

# ==========================================================
# LOGGING
# ==========================================================

logger.remove()

logger.add(

    sys.stdout,

    level="INFO",

    enqueue=True,

    backtrace=True,

    diagnose=False
)

logging.basicConfig(
    level=logging.INFO
)

logger.info(
    "✅ LOGGER INITIALIZED"
)

# ==========================================================
# BASE DIRECTORY
# ==========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

print(
    f"✅ BASE_DIR: {BASE_DIR}"
)

# ==========================================================
# SETTINGS
# ==========================================================

try:

    from app.core.config import settings

    print(
        "✅ SETTINGS IMPORTED"
    )

except Exception as e:

    print(
        "❌ SETTINGS IMPORT FAILED"
    )

    print(str(e))

    traceback.print_exc()

    class DummySettings:

        SECRET_KEY = "trustlytics-secret"

    settings = DummySettings()

# ==========================================================
# DATABASE
# ==========================================================

init_models = None
check_database_connection = None
close_database = None

try:

    from app.core.db import (

        init_models,

        check_database_connection,

        close_database
    )

    print(
        "✅ DATABASE MODULE IMPORTED"
    )

except Exception as e:

    print(
        "❌ DATABASE MODULE FAILED"
    )

    print(str(e))

    traceback.print_exc()

# ==========================================================
# FASTAPI LIFESPAN
# ==========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info(
        "🚀 APPLICATION STARTUP"
    )

    # ======================================================
    # DATABASE HEALTH CHECK
    # ======================================================

    try:

        if check_database_connection:

            db_status = await check_database_connection()

            if db_status:

                logger.success(
                    "✅ DATABASE CONNECTION HEALTHY"
                )

            else:

                logger.warning(
                    "⚠️ DATABASE CONNECTION FAILED"
                )

    except Exception as e:

        logger.error(
            f"❌ DATABASE HEALTH CHECK FAILED: {e}"
        )

    # ======================================================
    # DATABASE INITIALIZATION
    # ======================================================

    try:

        if init_models:

            logger.info(
                "📦 DATABASE INIT STARTED"
            )

            await init_models()

            logger.success(
                "✅ DATABASE INITIALIZED"
            )

        else:

            logger.warning(
                "⚠️ DATABASE INIT SKIPPED"
            )

    except Exception as e:

        logger.error(
            f"❌ DATABASE INIT FAILED: {e}"
        )

        logger.error(
            traceback.format_exc()
        )

    logger.success(
        "✅ APPLICATION STARTUP COMPLETE"
    )

    yield

    # ======================================================
    # SHUTDOWN
    # ======================================================

    logger.info(
        "🛑 APPLICATION SHUTDOWN"
    )

    try:

        if close_database:

            await close_database()

            logger.success(
                "✅ DATABASE CLOSED"
            )

    except Exception as e:

        logger.error(
            f"❌ DATABASE SHUTDOWN ERROR: {e}"
        )

# ==========================================================
# FASTAPI APP
# ==========================================================

app = FastAPI(

    title="Trustlytics AI",

    description="Enterprise AI Review Intelligence SaaS",

    version="3.0.0",

    lifespan=lifespan
)

print(
    "✅ FASTAPI APP CREATED"
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

            "success": False,

            "message": str(exc)
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

    allow_headers=["*"]
)

print(
    "✅ CORS ENABLED"
)

# ==========================================================
# SESSION MIDDLEWARE
# ==========================================================

SECRET_KEY = getattr(

    settings,

    "SECRET_KEY",

    "trustlytics-secret"
)

app.add_middleware(

    SessionMiddleware,

    secret_key=SECRET_KEY,

    session_cookie="trustlytics_session",

    max_age=86400,

    same_site="lax",

    https_only=False
)

print(
    "✅ SESSION ENABLED"
)

# ==========================================================
# TEMPLATES
# ==========================================================

TEMPLATE_DIR = os.path.join(

    BASE_DIR,

    "templates"
)

templates = None

if os.path.exists(TEMPLATE_DIR):

    templates = Jinja2Templates(
        directory=TEMPLATE_DIR
    )

    print(
        "✅ TEMPLATES LOADED"
    )

else:

    print(
        "⚠️ TEMPLATES DIRECTORY MISSING"
    )

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

        StaticFiles(
            directory=STATIC_DIR
        ),

        name="static"
    )

    print(
        "✅ STATIC FILES MOUNTED"
    )

else:

    print(
        "⚠️ STATIC DIRECTORY MISSING"
    )

# ==========================================================
# ROOT ROUTE
# ==========================================================

@app.get("/")

async def root():

    return RedirectResponse(

        url="/login",

        status_code=302
    )

# ==========================================================
# LOGIN PAGE
# ==========================================================

@app.get("/login", response_class=HTMLResponse)

async def login_page(
    request: Request
):

    try:

        if templates:

            return templates.TemplateResponse(

                "login.html",

                {

                    "request": request
                }
            )

    except Exception as e:

        logger.error(
            f"❌ LOGIN TEMPLATE ERROR: {e}"
        )

    return HTMLResponse(

        "<h1>Login Page Missing</h1>"
    )

# ==========================================================
# REGISTER PAGE
# ==========================================================

@app.get("/register", response_class=HTMLResponse)

async def register_page(
    request: Request
):

    try:

        if templates:

            return templates.TemplateResponse(

                "register.html",

                {

                    "request": request
                }
            )

    except Exception as e:

        logger.error(
            f"❌ REGISTER TEMPLATE ERROR: {e}"
        )

    return HTMLResponse(

        "<h1>Register Page Missing</h1>"
    )

# ==========================================================
# DASHBOARD PAGE
# ==========================================================

@app.get("/dashboard", response_class=HTMLResponse)

async def dashboard_page(
    request: Request
):

    try:

        if templates:

            return templates.TemplateResponse(

                "dashboard.html",

                {

                    "request": request
                }
            )

    except Exception as e:

        logger.error(
            f"❌ DASHBOARD TEMPLATE ERROR: {e}"
        )

    return HTMLResponse(

        "<h1>Dashboard Page Missing</h1>"
    )

# ==========================================================
# COMPANIES PAGE
# ==========================================================

@app.get("/companies", response_class=HTMLResponse)

async def companies_page(
    request: Request
):

    try:

        if templates:

            return templates.TemplateResponse(

                "companies.html",

                {

                    "request": request
                }
            )

    except Exception as e:

        logger.error(
            f"❌ COMPANIES TEMPLATE ERROR: {e}"
        )

    return HTMLResponse(

        "<h1>Companies Page Missing</h1>"
    )

# ==========================================================
# HEALTH CHECK
# ==========================================================

@app.get("/health")

async def health_check():

    return {

        "success": True,

        "service": "Trustlytics AI",

        "status": "healthy",

        "timestamp": datetime.utcnow().isoformat()
    }

# ==========================================================
# ROUTE LOADER
# ==========================================================

ROUTES = [

    "auth",

    "companies",

    "dashboard",

    "reviews",

    "chatbot",

    "reports"
]

# ==========================================================
# SAFE ROUTER REGISTRATION
# ==========================================================

for route_name in ROUTES:

    try:

        logger.info(
            f"📦 Loading Route: {route_name}"
        )

        module = __import__(

            f"app.routes.{route_name}",

            fromlist=["router"]
        )

        router = getattr(

            module,

            "router"
        )

        app.include_router(router)

        print(
            f"✅ {route_name.upper()} ROUTER REGISTERED"
        )

    except Exception as e:

        print(
            f"❌ {route_name.upper()} ROUTER FAILED"
        )

        print(str(e))

        traceback.print_exc()

# ==========================================================
# STARTUP COMPLETE
# ==========================================================

print(
    "✅ MAIN.PY FULLY LOADED"
)

# ==========================================================
# MAIN
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

        reload=False,

        log_level="info"
    )
