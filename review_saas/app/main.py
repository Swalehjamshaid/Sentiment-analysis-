from __future__ import annotations

import logging
import os
import sys
import secrets
import resend  # Requires 'resend' in requirements.txt
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

# --------------------------- Absolute Path Resolution ---------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# PARENT_DIR handles the /app/ vs /app/app structure
PARENT_DIR = os.path.dirname(CURRENT_DIR)

if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

def resolve_path(folder_name: str) -> str:
    """Finds templates/static in both local and parent directories."""
    local_path = os.path.join(CURRENT_DIR, folder_name)
    parent_path = os.path.join(PARENT_DIR, folder_name)
    if os.path.exists(local_path):
        return local_path
    return parent_path

TEMPLATE_DIR = resolve_path("templates")
STATIC_DIR = resolve_path("static")

# --------------------------- Core Imports ---------------------------
from app.core.config import settings
from app.core.db import get_engine
from app.core.models import Base, SCHEMA_VERSION

# --- Routers ---
try:
    from app.routes import auth as auth_routes
    from app.routes import companies as companies_routes
    from app.routes import dashboard as dashboard_routes
    from app.routes import reviews as reviews_routes
    from app.routes import exports as exports_routes
    from app.routes import google_check as google_routes
except ImportError as e:
    print(f"CRITICAL: Router import failed: {e}")
    # Fallback to prevent crash if some routes aren't created yet
    auth_routes = companies_routes = dashboard_routes = None

# --------------------------- Auth & Email Setup ---------------------------
ADMIN_EMAIL = "roy.jamshaid@gmail.com"
ADMIN_PASSWORD = "Jamshaid,1981"

# Initialize Resend
resend.api_key = os.getenv("RESEND_API_KEY", "re_D8MWpa1c_44ph6mZDfDoCXmEkeoYtPQqC")

# Store for magic links (In-memory for now; use Redis for multi-instance production)
MAGIC_TOKENS: Dict[str, Dict[str, Any]] = {}

# --------------------------- Logging ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("app.main")

# --------------------------- Email Helper ---------------------------
async def send_magic_link_email(to_email: str, token: str):
    """Triggers the Resend API to send the login link."""
    domain = os.getenv("DOMAIN_NAME", "https://sentiment-analysis-production-f96a.up.railway.app")
    verify_url = f"{domain}/verify?token={token}"
    
    try:
        params = {
            "from": "Review Intel AI <onboarding@resend.dev>",
            "to": [to_email],
            "subject": "Sign in to Review Intel AI",
            "html": f"""
                <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px; text-align: center;">
                    <h2 style="color: #4f46e5;">Review Intel AI</h2>
                    <p>Click the button below to sign in. This link expires in 15 minutes.</p>
                    <a href="{verify_url}" style="display: inline-block; background-color: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">Login to Dashboard</a>
                    <hr style="margin: 20px 0; border: 0; border-top: 1px solid #e2e8f0;" />
                    <p style="font-size: 12px; color: #64748b;">If you did not request this, please ignore this email.</p>
                </div>
            """
        }
        resend.Emails.send(params)
        logger.info(f"📧 Magic link sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"❌ Resend Error: {e}")
        return False

# --------------------------- Lifespan (DB & Client Init) ---------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB Tables
    try:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info(f"✅ Schema version {SCHEMA_VERSION} verified.")
    except Exception as e:
        logger.error(f"❌ DB Startup Failure: {e}")

    # Initialize Async HTTP Client for Outscraper
    app.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
    yield
    await app.state.http_client.aclose()

# --------------------------- App Initialization ---------------------------
app = FastAPI(title="Review Intel AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Secure Session Middleware
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Mount Static Files
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATE_DIR)

# Helper to check session
def get_current_user(request: Request) -> Optional[dict]:
    return request.session.get("user")

# --------------------------- Auth Logic Routes ---------------------------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user: Optional[dict] = Depends(get_current_user)):
    return RedirectResponse(url="/dashboard" if user else "/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None, message: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error, "message": message})

@app.post("/login")
async def handle_login(request: Request, email: str = Form(...), password: str = Form(None)):
    # 1. ADMIN BYPASS (Using your requested credentials)
    if email.lower() == ADMIN_EMAIL.lower() and password == ADMIN_PASSWORD:
        request.session["user"] = {"email": email, "name": "Admin Swaleh", "role": "admin"}
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    # 2. MAGIC LINK FLOW
    token = secrets.token_urlsafe(32)
    MAGIC_TOKENS[token] = {
        "email": email,
        "expires": datetime.now(timezone.utc) + timedelta(minutes=15)
    }
    
    success = await send_magic_link_email(email, token)
    if success:
        return templates.TemplateResponse("login.html", {
            "request": request, 
            "message": "✅ Magic link sent! Please check your inbox."
        })
    return templates.TemplateResponse("login.html", {
        "request": request, 
        "error": "❌ Email service error. Check Resend API Key."
    })

@app.get("/verify")
async def verify_token(request: Request, token: str):
    data = MAGIC_TOKENS.get(token)
    if not data or data["expires"] < datetime.now(timezone.utc):
        return RedirectResponse(url="/login?error=Link+expired+or+invalid")
    
    # Establish session
    request.session["user"] = {"email": data["email"], "name": "Authorized User", "role": "user"}
    del MAGIC_TOKENS[token]
    return RedirectResponse(url="/dashboard")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "user": user, 
        "google_api_key": settings.GOOGLE_API_KEY
    })

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

@app.get("/health")
async def health():
    return {"status": "ok", "version": SCHEMA_VERSION}

# --------------------------- Router Integration ---------------------------
if auth_routes: app.include_router(auth_routes.router)
if companies_routes: app.include_router(companies_routes.router)
if dashboard_routes: app.include_router(dashboard_routes.router)
if reviews_routes: app.include_router(reviews_routes.router)
if exports_routes: app.include_router(exports_routes.router)
if google_routes: app.include_router(google_routes.router)

# --------------------------- Execution ---------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
