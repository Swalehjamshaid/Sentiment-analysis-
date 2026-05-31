# ==========================================================
# FILE: app/main.py
# TRUSTLYTICS AI — WORLD-CLASS ENTERPRISE MAIN.PY
# COMPLETE VERSION — ALL ROUTES WORKING
# MAY 2026
# ==========================================================

from __future__ import annotations

import os
import sys
import traceback
import logging

from pathlib import Path

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
print(f"🐍 PYTHON VERSION: {sys.version}")
print("=" * 60)

# ==========================================================
# LOGGER CONFIG
# ==========================================================

logger.remove()

logger.add(
    sys.stdout,
    level="INFO",
    enqueue=True,
    backtrace=True,
    diagnose=False,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>"
)

logging.basicConfig(level=logging.INFO)

logger.info("✅ LOGGER INITIALIZED")

# ==========================================================
# BASE DIRECTORY
# ==========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
print(f"✅ BASE_DIR: {BASE_DIR}")

# ==========================================================
# REQUIRED DIRECTORIES
# ==========================================================

REQUIRED_DIRS = [
    os.path.join(BASE_DIR, "templates"),
    os.path.join(BASE_DIR, "static"),
    os.path.join(BASE_DIR, "static", "css"),
    os.path.join(BASE_DIR, "static", "reports"),
]

for directory in REQUIRED_DIRS:
    os.makedirs(directory, exist_ok=True)

logger.info("✅ REQUIRED DIRECTORIES VERIFIED")

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
        SECRET_KEY = "trustlytics-secret"
        DATABASE_URL = "sqlite:///./trustlytics.db"
    
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
    print("✅ DATABASE MODULE IMPORTED")
except Exception as e:
    print("❌ DATABASE MODULE FAILED")
    print(str(e))
    traceback.print_exc()

# ==========================================================
# TEMPLATE VALIDATION
# ==========================================================

def validate_required_files():
    required_files = [
        os.path.join(BASE_DIR, "templates", "executive_report.html"),
        os.path.join(BASE_DIR, "static", "css", "executive_theme.css"),
        os.path.join(BASE_DIR, "templates", "login.html"),
        os.path.join(BASE_DIR, "templates", "register.html"),
        os.path.join(BASE_DIR, "templates", "dashboard.html"),
        os.path.join(BASE_DIR, "templates", "companies.html"),
    ]

    for file_path in required_files:
        if os.path.exists(file_path):
            logger.success(f"✅ FILE VERIFIED => {os.path.basename(file_path)}")
        else:
            logger.warning(f"⚠️ FILE MISSING => {file_path}")

# ==========================================================
# LIFESPAN
# ==========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 APPLICATION STARTUP")

    # ======================================================
    # WEASYPRINT CHECK
    # ======================================================
    try:
        import weasyprint
        logger.success("✅ WEASYPRINT READY")
    except Exception as e:
        logger.error(f"❌ WEASYPRINT FAILED: {e}")

    # ======================================================
    # PLOTLY CHECK
    # ======================================================
    try:
        import plotly
        logger.success("✅ PLOTLY READY")
    except Exception as e:
        logger.error(f"❌ PLOTLY FAILED: {e}")

    # ======================================================
    # WORDCLOUD CHECK
    # ======================================================
    try:
        import wordcloud
        logger.success("✅ WORDCLOUD READY")
    except Exception as e:
        logger.error(f"❌ WORDCLOUD FAILED: {e}")

    # ======================================================
    # SPACY CHECK
    # ======================================================
    try:
        import spacy
        logger.success("✅ SPACY READY")
    except Exception as e:
        logger.error(f"❌ SPACY FAILED: {e}")

    # ======================================================
    # DATABASE HEALTH
    # ======================================================
    try:
        if check_database_connection:
            db_status = await check_database_connection()
            if db_status:
                logger.success("✅ DATABASE CONNECTION HEALTHY")
            else:
                logger.warning("⚠️ DATABASE CONNECTION FAILED")
    except Exception as e:
        logger.error(f"❌ DATABASE HEALTH CHECK FAILED: {e}")

    # ======================================================
    # DATABASE INIT
    # ======================================================
    try:
        if init_models:
            logger.info("📦 DATABASE INIT STARTED")
            await init_models()
            logger.success("✅ DATABASE INITIALIZED")
        else:
            logger.warning("⚠️ DATABASE INIT SKIPPED")
    except Exception as e:
        logger.error(f"❌ DATABASE INIT FAILED: {e}")
        logger.error(traceback.format_exc())

    # ======================================================
    # TEMPLATE VALIDATION
    # ======================================================
    validate_required_files()

    logger.success("🧠 EXECUTIVE REPORT ENGINE READY")
    logger.success("✅ APPLICATION STARTUP COMPLETE")

    yield

    # ======================================================
    # SHUTDOWN
    # ======================================================
    logger.info("🛑 APPLICATION SHUTDOWN")

    try:
        if close_database:
            await close_database()
            logger.success("✅ DATABASE CLOSED")
    except Exception as e:
        logger.error(f"❌ DATABASE SHUTDOWN ERROR: {e}")

# ==========================================================
# FASTAPI APP
# ==========================================================

app = FastAPI(
    title="Trustlytics AI",
    description="Enterprise AI Review Intelligence SaaS",
    version="4.0.0",
    lifespan=lifespan
)

print("✅ FASTAPI APP CREATED")

# ==========================================================
# GLOBAL ERROR HANDLER
# ==========================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"❌ GLOBAL ERROR => {request.url}")
    logger.error(traceback.format_exc())
    
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": str(exc),
            "path": str(request.url)
        }
    )

# ==========================================================
# CORS
# ==========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://trustlytics.online",
        "https://sentiment-analysis-production-f96a.up.railway.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("✅ CORS ENABLED")

# ==========================================================
# SESSION MIDDLEWARE
# ==========================================================

SECRET_KEY = getattr(settings, "SECRET_KEY", "trustlytics-secret")

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="trustlytics_session",
    max_age=86400,
    same_site="lax",
    https_only=False  # Set to True in production with HTTPS
)

print("✅ SESSION ENABLED")

# ==========================================================
# TEMPLATES
# ==========================================================

TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates: Jinja2Templates | None = None

if os.path.exists(TEMPLATE_DIR):
    templates = Jinja2Templates(directory=TEMPLATE_DIR)
    print("✅ TEMPLATES LOADED")
else:
    print("⚠️ TEMPLATES DIRECTORY MISSING")

# ==========================================================
# STATIC FILES
# ==========================================================

STATIC_DIR = os.path.join(BASE_DIR, "static")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    print("✅ STATIC FILES MOUNTED")
else:
    print("⚠️ STATIC DIRECTORY MISSING")

# ==========================================================
# ROOT REDIRECT
# ==========================================================

@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard", status_code=302)

# ==========================================================
# LOGIN PAGE
# ==========================================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    try:
        if templates:
            return templates.TemplateResponse("login.html", {"request": request})
        else:
            return HTMLResponse("<h1>Login Template Missing</h1><p>Templates directory not found</p>")
    except Exception as e:
        logger.error(f"❌ LOGIN TEMPLATE ERROR: {e}")
        return HTMLResponse(f"<h1>Login Template Error</h1><p>{str(e)}</p>")

# ==========================================================
# REGISTER PAGE
# ==========================================================

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    try:
        if templates:
            return templates.TemplateResponse("register.html", {"request": request})
        else:
            return HTMLResponse("<h1>Register Template Missing</h1>")
    except Exception as e:
        logger.error(f"❌ REGISTER TEMPLATE ERROR: {e}")
        return HTMLResponse(f"<h1>Register Template Error</h1><p>{str(e)}</p>")

# ==========================================================
# DASHBOARD PAGE
# ==========================================================

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    try:
        user_id = request.session.get("user_id")
        
        if not user_id:
            return RedirectResponse("/login")
        
        if templates:
            return templates.TemplateResponse(
                "dashboard.html",
                {
                    "request": request,
                    "user_id": user_id,
                    "user_name": request.session.get("user_name", "User")
                }
            )
        else:
            return HTMLResponse("<h1>Dashboard Template Missing</h1>")
    except Exception as e:
        logger.error(f"❌ DASHBOARD TEMPLATE ERROR: {e}")
        return HTMLResponse(f"<h1>Dashboard Template Error</h1><p>{str(e)}</p>")

# ==========================================================
# COMPANIES PAGE
# ==========================================================

@app.get("/companies-page", response_class=HTMLResponse)
async def companies_page(request: Request):
    try:
        if templates:
            return templates.TemplateResponse("companies.html", {"request": request})
        else:
            return HTMLResponse("<h1>Companies Template Missing</h1>")
    except Exception as e:
        logger.error(f"❌ COMPANIES TEMPLATE ERROR: {e}")
        return HTMLResponse(f"<h1>Companies Template Error</h1><p>{str(e)}</p>")

# ==========================================================
# LOGOUT
# ==========================================================

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)

# ==========================================================
# HEALTH CHECK
# ==========================================================

@app.get("/health")
async def health_check():
    return {
        "success": True,
        "service": "Trustlytics AI",
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "4.0.0"
    }

# ==========================================================
# DEBUG ROUTES ENDPOINT
# ==========================================================

@app.get("/debug/routes")
async def debug_routes():
    """Debug endpoint to see all registered routes"""
    routes = []
    for route in app.routes:
        routes.append({
            "path": route.path,
            "methods": list(route.methods) if hasattr(route, 'methods') else [],
            "name": getattr(route, 'name', 'unnamed')
        })
    
    # Sort by path
    routes.sort(key=lambda x: x['path'])
    
    return {
        "total_routes": len(routes),
        "routes": routes
    }

# ==========================================================
# ROUTES LIST
# ==========================================================

ROUTES = [
    "auth",
    "companies",
    "dashboard",
    "reviews",
    "chatbot",
    "reports",
]

# ==========================================================
# SAFE ROUTE LOADER WITH IMPROVED ERROR HANDLING
# ==========================================================

print("\n" + "=" * 60)
print("📦 LOADING ROUTES")
print("=" * 60)

for route_name in ROUTES:
    try:
        logger.info(f"📦 Loading Route: {route_name}")
        
        # Try different import paths
        module = None
        import_paths = [
            f"app.routes.{route_name}",
            f"routes.{route_name}",
            f".routes.{route_name}"
        ]
        
        for import_path in import_paths:
            try:
                module = __import__(import_path, fromlist=["router"])
                if hasattr(module, "router"):
                    break
                else:
                    module = None
            except ImportError:
                continue
        
        if module and hasattr(module, "router"):
            router = getattr(module, "router")
            app.include_router(router)
            prefix = getattr(router, "prefix", "/")
            logger.success(f"✅ {route_name.upper()} ROUTER REGISTERED (prefix: {prefix})")
        else:
            logger.error(f"❌ {route_name} has no 'router' attribute")
            
    except Exception as e:
        logger.error(f"❌ ROUTER IMPORT FAILED => {route_name}: {e}")
        logger.error(traceback.format_exc())

# ==========================================================
# DIRECT ROUTE REGISTRATION (FIX FOR CHATBOT)
# ==========================================================

print("\n" + "=" * 60)
print("🔧 DIRECT ROUTE REGISTRATION")
print("=" * 60)

# Direct import for chatbot to ensure it loads
try:
    from app.routes.chatbot import router as chatbot_router
    
    # Check if already registered
    is_registered = False
    for route in app.routes:
        if hasattr(route, 'path') and '/chatbot' in route.path:
            is_registered = True
            break
    
    if not is_registered:
        app.include_router(chatbot_router)
        logger.success("✅ CHATBOT ROUTER DIRECTLY REGISTERED")
    else:
        logger.info("ℹ️ CHATBOT ROUTER ALREADY REGISTERED")
        
except ImportError as e:
    logger.error(f"❌ DIRECT CHATBOT IMPORT FAILED: {e}")
    logger.error("   Make sure app/routes/chatbot.py exists and has a 'router' variable")
    
except Exception as e:
    logger.error(f"❌ DIRECT CHATBOT REGISTRATION FAILED: {e}")
    logger.error(traceback.format_exc())

# Direct import for auth router
try:
    from app.routes.auth import router as auth_router
    
    is_registered = False
    for route in app.routes:
        if hasattr(route, 'path') and '/auth' in route.path:
            is_registered = True
            break
    
    if not is_registered:
        app.include_router(auth_router)
        logger.success("✅ AUTH ROUTER DIRECTLY REGISTERED")
        
except ImportError as e:
    logger.error(f"❌ DIRECT AUTH IMPORT FAILED: {e}")
    
except Exception as e:
    logger.error(f"❌ DIRECT AUTH REGISTRATION FAILED: {e}")

# Direct import for companies router
try:
    from app.routes.companies import router as companies_router
    
    is_registered = False
    for route in app.routes:
        if hasattr(route, 'path') and '/companies' in route.path:
            is_registered = True
            break
    
    if not is_registered:
        app.include_router(companies_router)
        logger.success("✅ COMPANIES ROUTER DIRECTLY REGISTERED")
        
except ImportError as e:
    logger.error(f"❌ DIRECT COMPANIES IMPORT FAILED: {e}")
    
except Exception as e:
    logger.error(f"❌ DIRECT COMPANIES REGISTRATION FAILED: {e}")

# ==========================================================
# FINAL REGISTRATION SUMMARY
# ==========================================================

print("\n" + "=" * 60)
print("📊 REGISTERED ROUTES SUMMARY")
print("=" * 60)

registered_paths = []
for route in app.routes:
    if hasattr(route, 'path') and route.path:
        registered_paths.append(route.path)

# Group by prefix
chatbot_routes = [p for p in registered_paths if '/chatbot' in p]
auth_routes = [p for p in registered_paths if '/auth' in p]
api_routes = [p for p in registered_paths if '/api' in p]
dashboard_routes = [p for p in registered_paths if '/dashboard' in p or p == '/dashboard']

logger.info(f"📊 TOTAL ROUTES: {len(registered_paths)}")
logger.info(f"   - Chatbot routes: {len(chatbot_routes)}")
logger.info(f"   - Auth routes: {len(auth_routes)}")
logger.info(f"   - API routes: {len(api_routes)}")
logger.info(f"   - Dashboard routes: {len(dashboard_routes)}")

if chatbot_routes:
    logger.success("✅ CHATBOT ROUTES ACTIVE:")
    for route in chatbot_routes[:5]:
        logger.info(f"      → {route}")
else:
    logger.error("❌ NO CHATBOT ROUTES FOUND!")

# ==========================================================
# STARTUP COMPLETE
# ==========================================================

print("\n" + "=" * 60)
print("✅ MAIN.PY FULLY LOADED")
print("🚀 TRUSTLYTICS AI IS READY")
print("=" * 60)

# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")
    
    print(f"\n🚀 Starting server on {host}:{port}")
    print(f"📊 Dashboard: http://{host}:{port}/dashboard")
    print(f"🔍 Chatbot API: http://{host}:{port}/chatbot/health")
    print(f"🩺 Health Check: http://{host}:{port}/health")
    print(f"🐛 Debug Routes: http://{host}:{port}/debug/routes")
    print("\n")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,  # Set to False in production
        log_level="info",
        access_log=True
    )
