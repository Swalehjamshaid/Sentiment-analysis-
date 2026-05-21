# ==========================================================
# FILE: app/main.py
# TRUSTLYTICS AI — RAILWAY STABLE VERSION
# MAY 2026
# ==========================================================

import os
import sys
import traceback
import logging

from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from loguru import logger

# ==========================================================
# STARTUP DEBUG
# ==========================================================

print("🚀 TRUSTLYTICS STARTING")
print("🐍 PYTHON VERSION:", sys.version)

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

logging.basicConfig(level=logging.INFO)

logger.info("✅ Logger Initialized")

# ==========================================================
# BASE DIRECTORY
# ==========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

print(f"✅ BASE_DIR: {BASE_DIR}")

# ==========================================================
# SETTINGS IMPORT
# ==========================================================

try:

    from app.core.config import settings

    print("✅ Settings Imported")

except Exception as e:

    print("❌ SETTINGS IMPORT FAILED")
    print(str(e))

    class DummySettings:
        SECRET_KEY = "railway-secret"

    settings = DummySettings()

# ==========================================================
# DATABASE IMPORT
# ==========================================================

try:

    from app.core.db import init_models

    print("✅ Database Import Successful")

except Exception as e:

    print("❌ DATABASE IMPORT FAILED")
    print(str(e))

    init_models = None

# ==========================================================
# ROUTE IMPORTS
# ==========================================================

auth_router = None
companies_router = None
dashboard_router = None
reviews_router = None
chatbot_router = None
reports_router = None

try:

    from app.routes.auth import router as auth_router
    print("✅ AUTH ROUTE LOADED")

except Exception as e:

    print("❌ AUTH ROUTE FAILED")
    print(str(e))
    traceback.print_exc()

try:

    from app.routes.companies import router as companies_router
    print("✅ COMPANIES ROUTE LOADED")

except Exception as e:

    print("❌ COMPANIES ROUTE FAILED")
    print(str(e))
    traceback.print_exc()

try:

    from app.routes.dashboard import router as dashboard_router
    print("✅ DASHBOARD ROUTE LOADED")

except Exception as e:

    print("❌ DASHBOARD ROUTE FAILED")
    print(str(e))
    traceback.print_exc()

try:

    from app.routes.reviews import router as reviews_router
    print("✅ REVIEWS ROUTE LOADED")

except Exception as e:

    print("❌ REVIEWS ROUTE FAILED")
    print(str(e))
    traceback.print_exc()

try:

    from app.routes.chatbot import router as chatbot_router
    print("✅ CHATBOT ROUTE LOADED")

except Exception as e:

    print("❌ CHATBOT ROUTE FAILED")
    print(str(e))
    traceback.print_exc()

try:

    from app.routes.reports import router as reports_router
    print("✅ REPORTS ROUTE LOADED")

except Exception as e:

    print("❌ REPORTS ROUTE FAILED")
    print(str(e))
    traceback.print_exc()

# ==========================================================
# APPLICATION LIFESPAN
# ==========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("🚀 FastAPI Startup Initiated")

    # ======================================================
    # DATABASE INIT
    # ======================================================

    if init_models:

        try:

            logger.info("📦 Initializing Database")

            await init_models()

            logger.success("✅ Database Initialized")

        except Exception as e:

            logger.error("❌ Database Init Failed")
            logger.error(str(e))
            logger.error(traceback.format_exc())

    else:

        logger.warning("⚠️ Database Init Skipped")

    logger.success("✅ Application Startup Complete")

    yield

    logger.info("🛑 Application Shutdown Complete")

# ==========================================================
# FASTAPI APP
# ==========================================================

app = FastAPI(

    title="Trustlytics AI",

    description="AI Reputation & Review Intelligence Platform",

    version="3.0.0",

    lifespan=lifespan
)

print("✅ FastAPI App Created")

# ==========================================================
# GLOBAL ERROR HANDLER
# ==========================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):

    logger.error(f"❌ GLOBAL ERROR: {request.url}")

    logger.error(traceback.format_exc())

    return JSONResponse(

        status_code=500,

        content={

            "status": "error",

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

print("✅ CORS Enabled")

# ==========================================================
# SESSION MIDDLEWARE
# ==========================================================

SECRET_KEY = getattr(
    settings,
    "SECRET_KEY",
    "railway-secret"
)

app.add_middleware(

    SessionMiddleware,

    secret_key=SECRET_KEY
)

print("✅ Session Middleware Enabled")

# ==========================================================
# TEMPLATES
# ==========================================================

TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

if os.path.exists(TEMPLATE_DIR):

    templates = Jinja2Templates(directory=TEMPLATE_DIR)

    print("✅ Templates Loaded")

else:

    print("⚠️ Templates Directory Missing")

# ==========================================================
# STATIC FILES
# ==========================================================

STATIC_DIR = os.path.join(BASE_DIR, "static")

if os.path.exists(STATIC_DIR):

    app.mount(
        "/static",
        StaticFiles(directory=STATIC_DIR),
        name="static"
    )

    print("✅ Static Files Mounted")

else:

    print("⚠️ Static Directory Missing")

# ==========================================================
# ROOT ROUTE
# ==========================================================

@app.get("/")
async def root():

    return {

        "status": "running",

        "service": "Trustlytics AI",

        "version": "3.0.0"
    }

# ==========================================================
# HEALTH ROUTE
# ==========================================================

@app.get("/health")
async def health_check():

    return {

        "status": "healthy",

        "timestamp": datetime.utcnow().isoformat()
    }

# ==========================================================
# REGISTER ROUTERS
# ==========================================================

if auth_router:

    app.include_router(
        auth_router,
        prefix="/api/auth",
        tags=["Authentication"]
    )

if companies_router:

    app.include_router(
        companies_router,
        prefix="/api",
        tags=["Companies"]
    )

if dashboard_router:

    app.include_router(
        dashboard_router,
        prefix="/api",
        tags=["Dashboard"]
    )

if reviews_router:

    app.include_router(
        reviews_router,
        prefix="/api",
        tags=["Reviews"]
    )

if chatbot_router:

    app.include_router(
        chatbot_router,
        prefix="/api",
        tags=["Chatbot"]
    )

if reports_router:

    app.include_router(
        reports_router,
        tags=["Reports"]
    )

print("✅ Router Registration Completed")

# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(

        "app.main:app",

        host="0.0.0.0",

        port=int(os.environ.get("PORT", 8080)),

        reload=False,

        log_level="info"
    )
