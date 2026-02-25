# FILE: app/main.py

import os
import logging
from pathlib import Path
from typing import Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import secrets

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from markupsafe import Markup

from .db import init_db, get_db
from .models import Company, User, Review
from .services.rbac import get_current_user
from .context import common_context
from .routes import auth, companies, reviews, reply, reports, dashboard
from .routes.maps_routes import router as maps_router
from .routes.activity import router as activity_router
from .routes.insights import router as insights_router
from .dependencies import manager

# Import Metrics and AI services for real data fetching
from .services import metrics as metrics_svc
from .services import ai_insights as ai_svc

# ─────────────────────────────────────────────────────────────
# Paths, Logging, and Settings (Keep existing)
# ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

if not TEMPLATE_DIR.exists():
    TEMPLATE_DIR = PROJECT_ROOT / "app" / "templates"
if not STATIC_DIR.exists():
    STATIC_DIR = PROJECT_ROOT / "app" / "static"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("review_saas")

class Settings:
    APP_NAME: str = "ReviewSaaS"
    FORCE_HTTPS: bool = bool(int(os.getenv("FORCE_HTTPS", "0")))
    CORS_ALLOW_ORIGINS: str = os.getenv("CORS_ALLOW_ORIGINS", "*")
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", secrets.token_urlsafe(32))

settings = Settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db(drop_existing=os.getenv("DROP_ALL_TABLES") == "1")
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.exception("Database initialization failed: %s", e)
    yield

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# ─────────────────────────────────────────────────────────────
# Middleware (Keep existing)
# ─────────────────────────────────────────────────────────────
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET)

class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        if settings.FORCE_HTTPS and scheme != "https":
            return RedirectResponse(request.url.replace(scheme="https"), status_code=307)
        return await call_next(request)

app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ─────────────────────────────────────────────────────────────
# Filters (Keep existing)
# ─────────────────────────────────────────────────────────────
def format_date(value, fmt="%b %d, %Y"):
    if value is None: return ""
    mapping = {'Y-m-d': '%Y-%m-%d', 'd-m-Y': '%d-%m-%Y', 'H:i': '%H:%M', 'M d, Y': '%b %d, %Y'}
    fmt = mapping.get(fmt, fmt)
    if isinstance(value, str):
        try: value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except: return value
    return value.strftime(fmt)

templates.env.filters["date"] = format_date
templates.env.globals["now"] = lambda: datetime.now(timezone.utc)
templates.env.globals["csrf_token"] = lambda request: Markup(f'<input type="hidden" name="csrf_token" value="{request.session.get("_csrf", "")}">')

# ─────────────────────────────────────────────────────────────
# REAL DATA Local Routes
# ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if user:
        # If logged in, redirect to their first company dashboard
        user_db = db.query(User).filter(User.id == user.id).first()
        if user_db and user_db.companies:
            return RedirectResponse(f"/dashboard/{user_db.companies[0].id}")
    
    # Otherwise, show landing/empty dashboard state
    context = common_context(request)
    context.update({
        "current_user": user, "companies": [], "selected_company": None,
        "kpi": {"avg_rating": 0, "review_count": 0, "sentiment_score": 0, "growth": "0%"},
        "charts": {"labels": [], "sentiment": [], "rating": []},
        "reviews": [], "summary": "Login to see real data."
    })
    return templates.TemplateResponse("dashboard.html", context)

@app.get("/dashboard/{company_id}", response_class=HTMLResponse)
async def dashboard_view(request: Request, company_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")

    # Fetch Real Company Data
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return RedirectResponse("/")

    # Fetch Real Metrics (Last 30 days by default)
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=30)
    
    real_kpi = metrics_svc.build_kpi_for_dashboard(db, company_id, start_date, end_date)
    real_charts = metrics_svc.build_dashboard_charts(db, company_id, start_date, end_date)
    
    # Fetch Real Reviews
    real_reviews = db.query(Review).filter(Review.company_id == company_id).order_by(Review.review_date.desc()).limit(10).all()
    
    # Generate Real AI Summary
    ai_analysis = ai_svc.analyze_reviews(real_reviews, company, start_date, end_date)

    context = common_context(request)
    context.update({
        "current_user": user,
        "selected_company": company,
        "active_company": company,
        "companies": db.query(Company).filter(Company.owner_id == user.id).all(),
        "kpi": real_kpi,
        "charts": real_charts,
        "reviews": real_reviews,
        "summary": ai_analysis.get("summary_text", "No summary available."),
        "params": {"from": start_date.date().isoformat(), "to": end_date.date().isoformat(), "range": "30d"}
    })
    return templates.TemplateResponse("dashboard.html", context)

# ─────────────────────────────────────────────────────────────
# Auth & Router Inclusion (Keep existing)
# ─────────────────────────────────────────────────────────────

@app.post("/login")
async def login_post(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = await auth.login_post(request, email, password, db)
    if user:
        request.session["user_id"] = user.id
        # Get first company for this user
        comp = db.query(Company).filter(Company.owner_id == user.id).first()
        return RedirectResponse(f"/dashboard/{comp.id}" if comp else "/dashboard/0", status_code=302)
    return RedirectResponse("/login?error=1")

# Include all routers
app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(reviews.router)
app.include_router(reply.router)
app.include_router(reports.router)
app.include_router(dashboard.router) 
app.include_router(maps_router)
app.include_router(activity_router, prefix="/api/activity", tags=["telemetry"])
app.include_router(insights_router, prefix="/api/insights", tags=["ai"])

@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.APP_NAME}
