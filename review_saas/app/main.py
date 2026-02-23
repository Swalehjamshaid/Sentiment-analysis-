# Filename: main.py

import os
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from .db import engine
from .models import Base, Company
from .routes import auth, companies, reviews, reply, reports, dashboard, admin
from .routes.maps_routes import router as maps_router

# Routers aligned with the dashboard architecture
from .routes.activity import router as activity_router     # /api/activity – UI telemetry
from .routes.insights import router as insights_router     # /api/insights – AI summaries & recs

# Optional app config (fallback-safe)
try:
    from .core.config import settings
except Exception:
    # Minimal fallback if settings is not available
    class _Settings:
        APP_NAME: str = "ReviewSaaS"
        FORCE_HTTPS: bool = bool(int(os.getenv("FORCE_HTTPS", "0")))
        CORS_ALLOW_ORIGINS: str = os.getenv("CORS_ALLOW_ORIGINS", "*")
    settings = _Settings()

# ───────────────────────────────────────────────────────────────
# HTTPS Redirect Middleware
# ───────────────────────────────────────────────────────────────
class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if getattr(settings, "FORCE_HTTPS", False) and proto != "https":
            url = request.url.replace(scheme="https")
            return RedirectResponse(url, status_code=307)
        return await call_next(request)

# ───────────────────────────────────────────────────────────────
# FastAPI app initialization
# ───────────────────────────────────────────────────────────────
app = FastAPI(title=getattr(settings, "APP_NAME", "ReviewSaaS"))
templates = Jinja2Templates(directory="app/templates")

# Middlewares
app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)

# CORS – allow configured origins or all (* for rapid dev)
_allow_origins = getattr(settings, "CORS_ALLOW_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allow_origins.split(",")] if _allow_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static and uploads
if os.path.isdir("app_uploads"):
    app.mount("/uploads", StaticFiles(directory="app_uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ───────────────────────────────────────────────────────────────
# Database initialization
# ───────────────────────────────────────────────────────────────
@app.on_event("startup")
def _init_db():
    # Create tables if not exist
    Base.metadata.create_all(bind=engine)

    # Optional destructive reset for companies via env var
    if os.getenv("RECREATE_COMPANIES") == "1":
        print("!!! DROPPING AND RECREATING COMPANIES TABLE !!!")
        Base.metadata.drop_all(bind=engine, tables=[Company.__table__])
        Base.metadata.create_all(bind=engine)
        print("Companies table recreated.")

# ───────────────────────────────────────────────────────────────
# Template context – Inject important client-side config
# ───────────────────────────────────────────────────────────────
def template_context(request: Request) -> Dict[str, Any]:
    """
    Provide a minimal, safe context for public templates:
    - `apiBase`: base path for fetch calls from the front-end.
    - `googleMapsKey`: available to dashboard.html for map initialization.
    - `current_user`: None (auth disabled on this UI layer).
    """
    # Expose API base for frontend fetch() calls – stays empty for same-origin
    api_base = ""

    # Provide Maps key from ENV (fallback to known value if set in container)
    google_maps_key = os.getenv(
        "GOOGLE_MAPS_API_KEY",
        "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg",  # fallback for dev
    )

    return {
        "request": request,
        "current_user": None,            # Public UI; auth routed separately
        "apiBase": api_base,
        "googleMapsKey": google_maps_key,
    }

# Also set globals so Jinja templates can access without passing explicitly
templates.env.globals["apiBase"] = ""
templates.env.globals["googleMapsKey"] = os.getenv(
    "GOOGLE_MAPS_API_KEY",
    "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg",
)

# ───────────────────────────────────────────────────────────────
# UI Pages
# ───────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home(context: dict = Depends(template_context)):
    return templates.TemplateResponse("home.html", context)

@app.get("/register", response_class=HTMLResponse)
def register_page(context: dict = Depends(template_context)):
    return templates.TemplateResponse("register.html", context)

@app.get("/login", response_class=HTMLResponse)
def login_page(context: dict = Depends(template_context)):
    return templates.TemplateResponse("login.html", context)

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(context: dict = Depends(template_context)):
    # dashboard.html uses:
    #  - fetch('/api/reviews/summary/{company_id}')
    #  - fetch('/api/companies', '/api/companies/datatable', etc.)
    #  - googleMapsKey injected for map init
    return templates.TemplateResponse("dashboard.html", context)

@app.get("/companies", response_class=HTMLResponse)
def companies_page(context: dict = Depends(template_context)):
    return templates.TemplateResponse("companies.html", context)

@app.get("/report", response_class=HTMLResponse)
def report_page(context: dict = Depends(template_context)):
    return templates.TemplateResponse("report.html", context)

# ───────────────────────────────────────────────────────────────
# API Routers
# ───────────────────────────────────────────────────────────────
# NOTE:
# - `dashboard.router` exposes /api/* endpoints used by dashboard.html
# - `activity_router` provides POST /api/activity (telemetry)
# - `insights_router` provides GET /api/insights (AI panel)
app.include_router(auth.router, prefix="/auth")
app.include_router(companies.router)     # /api/companies/*
app.include_router(reviews.router)       # /api/reviews/*
app.include_router(reply.router)         # /api/reply/*
app.include_router(reports.router)       # /api/reports/*
app.include_router(dashboard.router)     # /api/* from routes/dashboard.py
app.include_router(admin.router)         # /api/admin/*
app.include_router(maps_router)          # /api/maps/*

# Always-record activity & AI insights
app.include_router(activity_router)
app.include_router(insights_router)

# ───────────────────────────────────────────────────────────────
# Health & diagnostics
# ───────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True}

@app.get("/env-diagnostics")
def env_diagnostics():
    # Helps verify keys are present when front-end looks empty
    return JSONResponse({
        "google_maps_key_present": bool(os.getenv("GOOGLE_MAPS_API_KEY")),
        "google_business_key_present": bool(os.getenv("GOOGLE_BUSINESS_API_KEY")),
        "google_places_key_present": bool(os.getenv("GOOGLE_PLACES_API_KEY")),
        "force_https": getattr(settings, "FORCE_HTTPS", False),
        "static_mounted": True,
    })
