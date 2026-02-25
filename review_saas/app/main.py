# filename: app/main.py
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

# Internal imports
from app.db import init_db
from app.models import User, Company, Review, KPI
from app.auth import get_current_user
from app.google_maps import google_maps_client

# -------------------------
# Logging setup
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("review_saas")

# -------------------------
# Paths (ABSOLUTE)
# -------------------------
BASE_DIR = Path(__file__).resolve().parent            # /app/app
TEMPLATES_DIR = BASE_DIR / "templates"               # /app/app/templates
STATIC_DIR = BASE_DIR / "static"                     # /app/app/static

# -------------------------
# Initialize FastAPI
# -------------------------
app = FastAPI(title="Review SaaS Dashboard", version="1.0.0")

# -------------------------
# Middleware
# -------------------------
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "supersecret"))
app.add_middleware(GZipMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# -------------------------
# Static & Templates (ABSOLUTE)
# -------------------------
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# -------------------------
# Database Initialization
# -------------------------
@app.on_event("startup")
async def startup_event():
    logger.info("Ensuring tables exist...")
    init_db()
    logger.info("Database initialized successfully.")

# -------------------------
# Safe Template Context
# -------------------------
def get_safe_context(request: Request, user: Optional[User] = None) -> Dict[str, Any]:
    """
    Build a safe context for rendering templates.
    Provides defaults to avoid Jinja2 crashes if variables are missing.
    NOTE: We keep names the same (user, companies, reviews, etc.) to avoid breaking templates.
    """
    # Default shells to keep templates happy even if DB calls fail
    companies = []
    active_company = None
    kpi: Dict[str, Any] = {}
    reviews = []
    roles = []

    # Fetch minimal data; wrap in try so a DB hiccup doesn't 500 the page
    try:
        companies = Company.get_all() or []
        active_company = companies[0] if companies else None
    except Exception as e:
        logger.exception("Failed to load companies for context: %s", e)

    try:
        if active_company:
            kpi = KPI.get_for_company(active_company.id) or {}
    except Exception as e:
        logger.exception("Failed to load KPI for context: %s", e)

    try:
        if active_company:
            reviews = Review.get_for_company(active_company.id) or []
    except Exception as e:
        logger.exception("Failed to load reviews for context: %s", e)

    try:
        # Avoid forcing lazy loads; if roles is a relationship, coerce to a list now
        roles = list(getattr(user, "roles", []) or []) if user else []
    except Exception as e:
        logger.exception("Failed to read user roles for context: %s", e)
        roles = []

    charts = {
        "labels": ["Jan", "Feb", "Mar"],
        "sentiment": [0, 0, 0],
        "rating": [0, 0, 0],
        "dist": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
        "correlation": [],
        "benchmark": {"labels": [], "series": []},
    }

    summary = "No summary available."
    alerts = []  # Placeholder; can be populated later

    return {
        "request": request,
        "user": user,
        "companies": companies,
        "active_company": active_company,
        "kpi": kpi,
        "charts": charts,
        "summary": summary,
        "reviews": reviews,
        "alerts": alerts,
        "roles": roles,
        "params": {},
        "csrf_token": lambda: "dummy_csrf_token",  # Replace with real CSRF if needed
    }

# -------------------------
# Routes
# -------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, user: User = Depends(get_current_user)):
    context = get_safe_context(request, user)
    # This will 500 if dashboard.html is missing; ensure file exists in app/templates
    return templates.TemplateResponse("dashboard.html", context)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_action(request: Request):
    form = await request.form()
    username = form.get("username")
    password = form.get("password")

    user = User.authenticate(username, password)
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    request.session.pop("user_id", None)
    return RedirectResponse("/login", status_code=302)

# -------------------------
# Google Maps Integration Example
# -------------------------
@app.get("/map_data")
async def map_data():
    try:
        data = google_maps_client.get_place_data("SomePlace")
        return {"success": True, "data": data}
    except Exception as e:
        logger.error(f"Google Maps API error: {e}")
        return {"success": False, "error": str(e)}

# -------------------------
# Error Handlers
# -------------------------
@app.exception_handler(404)
async def page_not_found(request: Request, exc):
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

@app.exception_handler(500)
async def server_error(request: Request, exc):
    logger.error("Server error: %s", exc)
    # Avoid risky DB calls here; keep the 500 page very light
    return templates.TemplateResponse("500.html", {"request": request, "error": str(exc)}, status_code=500)

# -------------------------
# Run command
# -------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), reload=True)
