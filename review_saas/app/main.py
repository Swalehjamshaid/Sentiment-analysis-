# filename: app/main.py
from __future__ import annotations

import os
import sys
import logging
import secrets
import resend  # Ensure 'resend' is in your requirements.txt
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Request, Depends, HTTPException, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

# ------------------------------------------------------------------------------
# 1. MODULE & PATH RESOLUTION (Fixes 'importlib' & ModuleNotFoundError)
# ------------------------------------------------------------------------------
# This block forces the Python interpreter to see the 'app' directory correctly
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) 
PARENT_DIR = os.path.dirname(CURRENT_DIR)

if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

def resolve_path(folder_name: str) -> str:
    """Detects templates/static in /app/app/ or /app/ for Railway/Docker."""
    local_path = os.path.join(CURRENT_DIR, folder_name)
    parent_path = os.path.join(PARENT_DIR, folder_name)
    return local_path if os.path.exists(local_path) else parent_path

TEMPLATE_DIR = resolve_path("templates")
STATIC_DIR = resolve_path("static")

# ------------------------------------------------------------------------------
# 2. CORE INTEGRATION (DB & MODELS)
# ------------------------------------------------------------------------------
from app.core.config import settings
from app.core.db import get_engine, init_models, Base
from app.core.models import SCHEMA_VERSION

# Import Routers with safety guards to prevent startup crashes
try:
    from app.routes import auth, companies, dashboard, reviews, exports, google_check
except ImportError as e:
    logging.error(f"⚠️ Router Import Warning: {e}")
    auth = companies = dashboard = reviews = exports = google_check = None

# ------------------------------------------------------------------------------
# 3. SETTINGS & AUTH CONFIGURATION
# ------------------------------------------------------------------------------
ADMIN_EMAIL = "roy.jamshaid@gmail.com"
ADMIN_PASSWORD = "Jamshaid,1981"

# Initialize Resend SDK
resend.api_key = os.getenv("RESEND_API_KEY", "re_D8MWpa1c_44ph6mZDfDoCXmEkeoYtPQqC")

# In-memory token store (Token -> {email, expires})
MAGIC_TOKENS: Dict[str, Dict[str, Any]] = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("app.main")

# ------------------------------------------------------------------------------
# 4. LIFESPAN (Database & Services Initialization)
# ------------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # This logic triggers the creation of the new 'CompanyCID' table
    logger.info(f"🚀 Initializing Review Intel AI - Schema Version: {SCHEMA_VERSION}")
    try:
        await init_models()
        logger.info("✅ Database logic synchronized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")

    # Global Async HTTP Client for API calls (Google/Outscraper)
    app.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
    yield
    # Cleanup on shutdown
    await app.state.http_client.aclose()

# ------------------------------------------------------------------------------
# 5. FASTAPI APP SETUP
# ------------------------------------------------------------------------------
app = FastAPI(title="Review Intel AI", version=SCHEMA_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATE_DIR)

def get_current_user(request: Request) -> Optional[dict]:
    return request.session.get("user")

# ------------------------------------------------------------------------------
# 6. AUTHENTICATION & DASHBOARD ROUTES
# ------------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Returns the current status and the SCHEMA_VERSION."""
    return {"status": "ok", "schema_version": SCHEMA_VERSION}

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user: Optional[dict] = Depends(get_current_user)):
    return RedirectResponse(url="/dashboard" if user else "/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None, message: Optional[str] = None):
    return templates.TemplateResponse("login.html", {
        "request": request, 
        "error": error, 
        "message": message
    })

@app.post("/login")
async def handle_login(request: Request, email: str = Form(...), password: str = Form(None)):
    # 1. ADMIN BRANCH: Direct Login
    if email.lower() == ADMIN_EMAIL.lower() and password == ADMIN_PASSWORD:
        request.session["user"] = {"email": email, "name": "Admin Jamshaid", "role": "admin"}
        logger.info(f"👑 Admin {email} logged in.")
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    # 2. USER BRANCH: Magic Link via Resend
    token = secrets.token_urlsafe(32)
    MAGIC_TOKENS[token] = {
        "email": email,
        "expires": datetime.now(timezone.utc) + timedelta(minutes=15)
    }
    
    try:
        domain = os.getenv("DOMAIN_NAME", "https://sentiment-analysis-production-f96a.up.railway.app")
        verify_url = f"{domain}/verify?token={token}"
        
        resend.Emails.send({
            "from": "Review Intel AI <onboarding@resend.dev>",
            "to": [email],
            "subject": "Sign in to Review Intel AI",
            "html": f"""
                <div style="font-family: sans-serif; max-width: 500px; margin: auto; padding: 20px; border: 1px solid #eee; border-radius: 10px; text-align: center;">
                    <h2 style="color: #4f46e5;">Review Intel AI</h2>
                    <p>Click the button below to sign in to your dashboard.</p>
                    <a href="{verify_url}" style="display: inline-block; background-color: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">Login to Dashboard</a>
                    <hr style="margin: 20px 0; border: 0; border-top: 1px solid #eee;" />
                    <p style="font-size: 11px; color: #999;">Link expires in 15 minutes.</p>
                </div>
            """
        })
        return templates.TemplateResponse("login.html", {"request": request, "message": "✅ Magic link sent! Please check your email inbox."})
    except Exception as e:
        logger.error(f"❌ Mailer Error: {e}")
        return templates.TemplateResponse("login.html", {"request": request, "error": "❌ Failed to send email. Verify Resend configuration."})

@app.get("/verify")
async def verify_token(request: Request, token: str):
    data = MAGIC_TOKENS.get(token)
    if not data or data["expires"] < datetime.now(timezone.utc):
        return RedirectResponse(url="/login?error=Link+expired+or+invalid")
    
    request.session["user"] = {"email": data["email"], "role": "user", "name": "Authorized User"}
    if token in MAGIC_TOKENS:
        del MAGIC_TOKENS[token]
    return RedirectResponse(url="/dashboard")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "user": user, 
        "google_api_key": getattr(settings, "GOOGLE_API_KEY", "")
    })

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

# ------------------------------------------------------------------------------
# 7. ROUTER REGISTRATION
# ------------------------------------------------------------------------------
if auth: app.include_router(auth.router)
if companies: app.include_router(companies.router)
if dashboard: app.include_router(dashboard.router)
if reviews: app.include_router(reviews.router)
if exports: app.include_router(exports.router)
if google_check: app.include_router(google_check.router)

# ------------------------------------------------------------------------------
# 8. PRODUCTION STARTUP
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
