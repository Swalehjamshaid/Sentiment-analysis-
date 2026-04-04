# filename: app/main.py
from __future__ import annotations
import os
import sys
import logging
import secrets
import resend
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
import httpx

# ------------------------------------------------------------------------------
# 0. SENTRY INITIALIZATION - MUST BE FIRST (to capture import errors)
# ------------------------------------------------------------------------------
import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
import logging as std_logging

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),   # ← Make sure this env var is set in Railway/Docker
    integrations=[
        AsyncioIntegration(),
        LoggingIntegration(
            level=std_logging.INFO,
            event_level=std_logging.ERROR,
        ),
    ],
    traces_sample_rate=0.2,
    environment=os.getenv("ENVIRONMENT", "production"),
    # send_default_pii=False,   # Uncomment in production if needed
)

# ------------------------------------------------------------------------------
# 1. MODULE & PATH RESOLUTION
# ------------------------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

def resolve_path(folder_name: str) -> str:
    """Detects templates/static in correct directory for Docker/Railway."""
    local_path = os.path.join(CURRENT_DIR, folder_name)
    parent_path = os.path.join(PARENT_DIR, folder_name)
    return local_path if os.path.exists(local_path) else parent_path

TEMPLATE_DIR = resolve_path("templates")
STATIC_DIR = resolve_path("static")

# ------------------------------------------------------------------------------
# 2. CORE INTEGRATION - SAFE IMPORTS
# ------------------------------------------------------------------------------
from app.core.config import settings
from app.core.db import get_engine, init_models, Base

# Safe SCHEMA_VERSION import
SCHEMA_VERSION = "unknown"
try:
    from app.core.models import SCHEMA_VERSION as ImportedSchemaVersion
    SCHEMA_VERSION = ImportedSchemaVersion
except Exception as e:
    logging.error(f"⚠️ Failed to import SCHEMA_VERSION from models.py", exc_info=True)

# Safe router imports (catch everything)
auth = companies = dashboard = reviews = exports = google_check = None
try:
    from app.routes import auth, companies, dashboard, reviews, exports, google_check
    logging.info("✅ All routers imported successfully.")
except Exception as e:
    logging.error(f"❌ Critical error while importing routers", exc_info=True)

# ------------------------------------------------------------------------------
# 3. SETTINGS & AUTH CONFIGURATION
# ------------------------------------------------------------------------------
ADMIN_EMAIL = "roy.jamshaid@gmail.com"
ADMIN_PASSWORD = "Jamshaid,1981"
resend.api_key = os.getenv("RESEND_API_KEY", "re_D8MWpa1c_44ph6mZDfDoCXmEkeoYtPQqC")

MAGIC_TOKENS: Dict[str, Dict[str, Any]] = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("app.main")

# ------------------------------------------------------------------------------
# 4. LIFESPAN (Safe database initialization)
# ------------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 Starting Review Intel AI - Schema Version: {SCHEMA_VERSION}")

    try:
        await init_models()
        logger.info("✅ Database models initialized successfully.")
    except Exception as e:
        logger.error("❌ Database initialization failed during startup", exc_info=True)
        raise RuntimeError(f"Startup failed: Database initialization error - {str(e)}") from e

    # Global Async HTTP Client
    app.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))

    yield

    # Cleanup
    await app.state.http_client.aclose()
    logger.info("🛑 Application shutdown completed.")

# ------------------------------------------------------------------------------
# 5. FASTAPI APP SETUP
# ------------------------------------------------------------------------------
from fastapi import FastAPI, Request, Depends, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

app = FastAPI(
    title="Review Intel AI",
    version=SCHEMA_VERSION,
    lifespan=lifespan
)

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
# 6. ROUTES
# ------------------------------------------------------------------------------
@app.get("/health")
async def health():
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
    if email.lower() == ADMIN_EMAIL.lower() and password == ADMIN_PASSWORD:
        request.session["user"] = {"email": email, "name": "Admin Jamshaid", "role": "admin"}
        logger.info(f"👑 Admin {email} logged in.")
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    # Magic link logic
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
        logger.error(f"❌ Mailer Error: {e}", exc_info=True)
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
# 7. ROUTER REGISTRATION (Safe)
# ------------------------------------------------------------------------------
for name, router_module in [("auth", auth), ("companies", companies), ("dashboard", dashboard),
                            ("reviews", reviews), ("exports", exports), ("google_check", google_check)]:
    if router_module and hasattr(router_module, "router"):
        try:
            app.include_router(router_module.router)
            logger.info(f"✅ Included router: {name}")
        except Exception as e:
            logger.error(f"❌ Failed to include router '{name}'", exc_info=True)

# ------------------------------------------------------------------------------
# 8. PRODUCTION STARTUP
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
