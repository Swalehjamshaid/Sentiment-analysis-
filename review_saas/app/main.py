# ==========================================================
# FILE: app/main.py
# TRUSTLYTICS AI — FINAL COMPLETE RAILWAY STABLE MAIN.PY
# MAY 2026 ENTERPRISE VERSION
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

print("🚀 TRUSTLYTICS AI STARTING")
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

logger.info("✅ LOGGER INITIALIZED")

# ==========================================================
# BASE DIR
# ==========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

print(f"✅ BASE_DIR: {BASE_DIR}")

# ==========================================================
# SETTINGS
# ==========================================================

try:

    from app.core.config import settings

    print("✅ SETTINGS IMPORTED")

except Exception as e:

    print("❌ SETTINGS IMPORT FAILED")
    print(str(e))
    traceback.print_exc()

    class DummySettings:
        SECRET_KEY = "railway-secret"

    settings = DummySettings()

# ==========================================================
# DATABASE
# ==========================================================

init_models = None

try:

    from app.core.db import init_models

    print("✅ DATABASE MODULE IMPORTED")

except Exception as e:

    print("❌ DATABASE MODULE FAILED")
    print(str(e))
    traceback.print_exc()

# ==========================================================
# FASTAPI LIFESPAN
# ==========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("🚀 APPLICATION STARTUP")

    # ======================================================
    # SAFE DATABASE INIT
    # ======================================================

    if init_models:

        try:

            logger.info("📦 DATABASE INIT STARTED")

            # ==================================================
            # IMPORTANT:
            # IF DATABASE CAUSES FREEZE,
            # COMMENT THIS AGAIN
            # ==================================================

            await init_models()

            logger.success("✅ DATABASE INITIALIZED")

        except Exception as e:

            logger.error("❌ DATABASE INIT FAILED")
            logger.error(str(e))
            logger.error(traceback.format_exc())

    else:

        logger.warning("⚠️ DATABASE INIT SKIPPED")

    logger.success("✅ APPLICATION STARTUP COMPLETE")

    yield

    logger.info("🛑 APPLICATION SHUTDOWN")

# ==========================================================
# FASTAPI APP
# ==========================================================

app = FastAPI(

    title="Trustlytics AI",

    description="AI Reputation Intelligence SaaS",

    version="3.0.0",

    lifespan=lifespan
)

print("✅ FASTAPI APP CREATED")

# ==========================================================
# GLOBAL ERROR HANDLER
# ==========================================================

@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception
):

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

print("✅ CORS ENABLED")

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

    secret_key=SECRET_KEY,

    session_cookie="trustlytics_session",

    max_age=86400,

    same_site="lax",

    https_only=False
)

print("✅ SESSION ENABLED")

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

    print("✅ TEMPLATES LOADED")

else:

    print("⚠️ TEMPLATES DIRECTORY MISSING")

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

    print("✅ STATIC FILES MOUNTED")

else:

    print("⚠️ STATIC DIRECTORY MISSING")

# ==========================================================
# ROOT ROUTES
# ==========================================================

@app.get("/")
async def root():

    return {

        "status": "running",

        "service": "Trustlytics AI",

        "version": "3.0.0"
    }

# ==========================================================
# HEALTH CHECK
# ==========================================================

@app.get("/health")
async def health_check():

    return {

        "status": "healthy",

        "timestamp": datetime.utcnow().isoformat()
    }

# ==========================================================
# SAFE ROUTER LOADER
# ==========================================================

ROUTES = [

    ("auth", "/api/auth"),

    ("companies", "/api"),

    ("dashboard", "/api"),

    ("reviews", "/api"),

    ("chatbot", "/api"),

    ("reports", "")
]

# ==========================================================
# ROUTER REGISTRATION
# ==========================================================

for route_name, prefix in ROUTES:

    try:

        logger.info(f"📦 Loading Route: {route_name}")

        module = __import__(

            f"app.routes.{route_name}",

            fromlist=["router"]
        )

        router = getattr(module, "router")

        app.include_router(
            router,
            prefix=prefix
        )

        print(f"✅ {route_name.upper()} ROUTER REGISTERED")

    except Exception as e:

        print(f"❌ {route_name.upper()} ROUTER FAILED")

        print(str(e))

        traceback.print_exc()

# ==========================================================
# STARTUP COMPLETE
# ==========================================================

print("✅ MAIN.PY FULLY LOADED")

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
