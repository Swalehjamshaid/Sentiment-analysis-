# filename: app/main.py
from __future__ import annotations

import logging
import os
import sys
import secrets
import resend  # Requires 'resend' in requirements.txt
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, List

import httpx
from fastapi import FastAPI, Request, Depends, HTTPException, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# --------------------------- Absolute Path Resolution ---------------------------
# CURRENT_DIR is /app/app/ | PARENT_DIR is /app/
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)

if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

def resolve_path(folder_name: str) -> str:
    """Finds templates/static in both local and parent directories for Docker/Railway."""
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
from app.routes import auth as auth_routes
from app.routes import companies as companies_routes
from app.routes import dashboard as dashboard_routes
from app.routes import reviews as reviews_routes
from app.routes import exports as exports_routes
from app.routes import google_check as google_routes

# --------------------------- Auth & Email Setup ---------------------------
# Admin Credentials as requested
ADMIN_EMAIL = "roy.jamshaid@gmail.com"
ADMIN_PASSWORD = "Jamshaid,1981"

# Initialize Resend with your API Key
resend.api_key = os.getenv("RESEND_API_KEY", "re_D8MWpa1c_44ph6mZDfDoCXmEkeoYtPQqC")

# Store for magic links (Token -> Data)
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
                <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px;">
                    <h2 style="color: #4f46e5;">Review Intel AI</h2>
                    <p>Click the button below to sign in to your dashboard. This link expires in 15 minutes.</p>
                    <a href="{verify_url}" style="display: inline-block; background-color: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">Login to Dashboard</a>
                    <hr style="margin: 20px 0; border: 0; border-top: 1px solid #e2e8f0;" />
                    <p style="font-size: 12px; color: #64748b;">If you did not request this email, you can safely ignore it.</p>
                </div>
            """
        }
        resend.Emails.send(params)
        logger.info(f"📧 Magic link email successfully sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"❌ Resend API Error: {e}")
        return False

# --------------------------- Outscraper Client ---------------------------
class OutscraperClient:
    BASE_URL = "https://api.app.outscraper.com/google-reviews"
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))
    async def get_reviews(self, place_id: str, limit: int = 200) -> Dict[str, Any]:
        try:
            params = {"query": place_id, "limit": limit, "async": "false"}
            headers = {"X-API-KEY": self.api_key}
            response = await self.client.get(self.BASE_URL, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return {"reviews": data[0].get("reviews_data", []) if data else []}
            return {"reviews": []}
        except Exception as e:
            logger.error(f"Outscraper Error: {e}")
            return {"reviews": []}
    async def close(self):
        await self.client.aclose()

# --------------------------- Lifespan ---------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        engine: AsyncEngine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Database schema verified.")
    except Exception as e:
        logger.error(f"❌ DB Startup Error: {e}")

    api_key = os.getenv("OUTSCRAPER_API_KEY") or getattr(settings, "OUTSCRAPER_API_KEY", None)
    app.state.reviews_client = OutscraperClient(api_key) if api_key else None
    yield
    if app.state.reviews_client:
        await app.state.reviews_client.close()

# --------------------------- App Setup ---------------------------
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

def get_current_user(request: Request) -> Optional[dict]:
    return request.session.get("user")

# --------------------------- Routes ---------------------------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    return RedirectResponse(url="/dashboard")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={})

@app.post("/login")
async def handle_login(request: Request, email: str = Form(...), password: str = Form(...)):
    # 1. ADMIN BRANCH: Direct access for you
    if email.lower() == ADMIN_EMAIL.lower() and password == ADMIN_PASSWORD:
        request.session["user"] = {"email": email, "name": "Admin Swaleh", "role": "admin"}
        logger.info(f"👑 Admin {email} logged in directly.")
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    # 2. GENERAL USER BRANCH: Magic Link via Resend API
    token = secrets.token_urlsafe(32)
    MAGIC_TOKENS[token] = {
        "email": email,
        "expires": datetime.now() + timedelta(minutes=15)
    }
    
    success = await send_magic_link_email(email, token)
    
    if success:
        return templates.TemplateResponse(
            request=request, 
            name="login.html", 
            context={"message": "✅ Magic link sent! Please check your email inbox."}
        )
    else:
        return templates.TemplateResponse(
            request=request, 
            name="login.html", 
            context={"error": "❌ Failed to send email. Check API key settings."}
        )

@app.get("/verify")
async def verify_token(request: Request, token: str):
    data = MAGIC_TOKENS.get(token)
    if not data or data["expires"] < datetime.now():
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Invalid or expired link."})
    
    # Establish session
    request.session["user"] = {"email": data["email"], "name": "Authorized User"}
    if token in MAGIC_TOKENS:
        del MAGIC_TOKENS[token]
    return RedirectResponse(url="/dashboard")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    
    return templates.TemplateResponse(
        request=request, 
        name="dashboard.html", 
        context={
            "user": user,
            "google_api_key": settings.GOOGLE_API_KEY
        }
    )

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

@app.get("/health")
async def health():
    return {"status": "ok", "schema_version": SCHEMA_VERSION}

# Include Routers
app.include_router(auth_routes.router)
app.include_router(companies_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)
app.include_router(google_routes.router)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
