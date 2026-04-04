# filename: app/main.py
from __future__ import annotations

import logging
import os
import sys
import secrets
import resend  # Ensure 'resend' is in your requirements.txt
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
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)

if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

def resolve_path(folder_name: str) -> str:
    """Check current and parent directories for the required folder."""
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
from app.core.models import Base, SCHEMA_VERSION, Company, Review

# --------------------------- Auth Config & API Setup ---------------------------
# Admin Credentials as requested
ADMIN_EMAIL = "roy.jamshaid@gmail.com"
ADMIN_PASSWORD = "Jamshaid,1981"

# Initialize Resend with the API key from your screenshot
# Note: It is best practice to set this in Railway Variables as RESEND_API_KEY
resend.api_key = os.getenv("RESEND_API_KEY", "re_D8MWpa1c_44ph6mZDfDoCXmEkeoYtPQqC")

# Store for magic links (Token -> Data)
MAGIC_TOKENS: Dict[str, Dict[str, Any]] = {}

# --------------------------- Logging ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
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

    async def get_reviews(self, place_id: str, limit: int = 200, offset: int = 0) -> Dict[str, Any]:
        try:
            params = {"query": place_id, "limit": limit, "offset": offset, "async": "false"}
            headers = {"X-API-KEY": self.api_key}
            response = await self.client.get(self.BASE_URL, params=params, headers=headers)
            
            if response.status_code != 200:
                return {"reviews": []}
            
            data = response.json()
            if isinstance(data, list) and data:
                return {"reviews": data[0].get("reviews_data", [])}
            return {"reviews": []}
        except Exception as e:
            logger.error("🚨 Outscraper Client Failure: %s", e)
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
        logger.error("❌ Database startup failed: %s", e)

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

# --------------------------- Auth Routes ---------------------------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/dashboard")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={})

@app.post("/login")
async def handle_login(request: Request, email: str = Form(...), password: str = Form(...)):
    # 1. ADMIN BRANCH: Direct Access
    if email.lower() == ADMIN_EMAIL.lower() and password == ADMIN_PASSWORD:
        user = {"id": 0, "email": email, "name": "Admin Swaleh", "role": "admin"}
        request.session["user"] = user
        logger.info(f"👑 Admin {email} logged in directly.")
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    # 2. GENERAL USER BRANCH: Magic Link
    token = secrets.token_urlsafe(32)
    MAGIC_TOKENS[token] = {
        "email": email,
        "expires": datetime.now() + timedelta(minutes=15)
    }
    
    email_success = await send_magic_link_email(email, token)
    
    if email_success:
        return templates.TemplateResponse(
            request=request, 
            name="login.html", 
            context={"message": "✅ Magic link sent! Check your inbox to finish logging in."}
        )
    else:
        return templates.TemplateResponse(
            request=request, 
            name="login.html", 
            context={"error": "❌ Error sending email. Please check your Resend configuration."}
        )

@app.get("/verify")
async def verify_login(request: Request, token: str):
    token_data = MAGIC_TOKENS.get(token)
    if not token_data or token_data["expires"] < datetime.now():
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Invalid or expired link."})
    
    request.session["user"] = {"email": token_data["email"], "name": "Authorized User"}
    del MAGIC_TOKENS[token]
    return RedirectResponse(url="/dashboard")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        request=request, 
        name="dashboard.html", 
        context={"user": user, "google_api_key": settings.GOOGLE_API_KEY}
    )

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

# Include Routers
app.include_router(dashboard_routes.router)
app.include_router(reviews_routes.router)
app.include_router(exports_routes.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080)
