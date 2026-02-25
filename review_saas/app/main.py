import os
import logging
import secrets
from pathlib import Path
from typing import Dict, Any, List
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from markupsafe import Markup
from jinja2 import pass_context

from .db import init_db, get_db
from .models import Company, User, Review
from .services.rbac import get_current_user
from .context import common_context
# Renaming dashboard import to avoid collision with local route function
from .routes import auth, companies, reviews, reply, reports, dashboard as dashboard_module
from .routes.maps_routes import router as maps_router
from .routes.activity import router as activity_router
from .routes.insights import router as insights_router
from .dependencies import manager

# Import Real Data Services
from .services import metrics as metrics_svc
from .services import ai_insights as ai_svc

# SAFE IMPORT FOR GOOGLE MAPS
try:
    from .services import google_maps as maps_svc
except ImportError:
    maps_svc = None
    logging.warning("Service 'google_maps' not found. Sync functionality will be disabled.")

# ─────────────────────────────────────────────────────────────
# Paths & Directories
# ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

if not TEMPLATE_DIR.exists():
    TEMPLATE_DIR = PROJECT_ROOT / "app" / "templates"
if not STATIC_DIR.exists():
    STATIC_DIR = PROJECT_ROOT / "app" / "static"

# ─────────────────────────────────────────────────────────────
# Logging & Settings
# ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("review_saas")

class Settings:
    APP_NAME: str = "ReviewSaaS"
    FORCE_HTTPS: bool = bool(int(os.getenv("FORCE_HTTPS", "0")))
    CORS_ALLOW_ORIGINS: str = os.getenv("CORS_ALLOW_ORIGINS", "*")
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "supersecretkey123")

settings = Settings()

# ─────────────────────────────────────────────────────────────
# Lifespan / Startup
# ─────────────────────────────────────────────────────────────
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
# Middleware
# ─────────────────────────────────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET,
    session_cookie="session",
    max_age=3600 * 24 * 7
)

class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        if settings.FORCE_HTTPS and scheme != "https":
            return RedirectResponse(request.url.replace(scheme="https"), status_code=307)
        return await call_next(request)

app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.CORS_ALLOW_ORIGINS] if settings.CORS_ALLOW_ORIGINS != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# ─────────────────────────────────────────────────────────────
# Templates & Jinja Environment
# ─────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

def format_date(value, fmt="%b %d, %Y"):
    if value is None: return ""
    mapping = {'Y-m-d': '%Y-%m-%d', 'd-m-Y': '%d-%m-%Y', 'H:i': '%H:%M', 'M d, Y': '%b %d, %Y'}
    fmt = mapping.get(fmt, fmt)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except:
            return value
    return value.strftime(fmt)

def _now():
    return datetime.now(timezone.utc)

@pass_context
def _csrf_token(context: dict):
    request = context.get("request")
    if not request: return ""
    token = request.session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["_csrf"] = token
    return Markup(f'<input type="hidden" name="csrf_token" value="{token}">')

templates.env.filters["date"] = format_date
templates.env.globals["now"] = _now
templates.env.globals["csrf_token"] = _csrf_token

# ─────────────────────────────────────────────────────────────
# Helper: Safe Context (Prevents 500 Rendering Errors)
# ─────────────────────────────────────────────────────────────
def get_safe_context(request: Request, current_user=None) -> dict:
    ctx = common_context(request)
    mock_company = {"id": 0, "name": "No Company Selected", "industry": "N/A", "created_at": datetime.now()}
    ctx.update({
        "current_user": current_user, "companies": [], "selected_company": mock_company,
        "active_company": mock_company, "params": {"from": "", "to": "", "range": ""},
        "kpi": {"avg_rating": 0, "review_count": 0, "sentiment_score": 0, "growth": "0%", "pos": 0, "neu": 0, "neg": 0},
        "charts": {"labels": [], "sentiment": [], "rating": []},
        "reviews": [], "summary": "Log in to see your real data.",
        "api_health": [], "alerts": [], "roles": []
    })
    return ctx

# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if user:
        user_db = db.query(User).filter(User.id == user.id).first()
        if user_db and user_db.companies:
            return RedirectResponse(f"/dashboard/{user_db.companies[0].id}")
    return templates.TemplateResponse("dashboard.html", get_safe_context(request, user))

@app.get("/login", response_class=HTMLResponse)
async def login_view(request: Request): 
    if get_current_user(request): return RedirectResponse("/")
    return templates.TemplateResponse("dashboard.html", get_safe_context(request))

@app.post("/login")
async def login_post(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    result = await auth.login_post(request, email, password, db)

    # 1. Catch Redirect (Failed Login)
    if isinstance(result, RedirectResponse):
        return result

    # 2. Handle Successful Login
    user = result
    if user and hasattr(user, 'id'):
        request.session["user_id"] = user.id
        first_comp = db.query(Company).filter(Company.owner_id == user.id).first()
        if first_comp:
            return RedirectResponse(f"/dashboard/{first_comp.id}", status_code=302)
        return RedirectResponse("/", status_code=302)
    
    # 3. Fallback
    context = get_safe_context(request)
    context["flash_error"] = "Invalid email or password."
    return templates.TemplateResponse("dashboard.html", context)

@app.get("/dashboard/{company_id}", response_class=HTMLResponse)
async def dashboard_view(request: Request, company_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user: return RedirectResponse("/login")

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company: return RedirectResponse("/")

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=30)
    
    kpi = metrics_svc.build_kpi_for_dashboard(db, company_id, start_date, end_date)
    charts = metrics_svc.build_dashboard_charts(db, company_id, start_date, end_date)
    reviews_list = db.query(Review).filter(Review.company_id == company_id).order_by(Review.review_date.desc()).limit(10).all()
    ai_summary = ai_svc.analyze_reviews(reviews_list, company, start_date, end_date)

    context = common_context(request)
    context.update({
        "current_user": user, "selected_company": company, "active_company": company,
        "companies": db.query(Company).filter(Company.owner_id == user.id).all(),
        "kpi": kpi, "charts": charts, "reviews": reviews_list,
        "summary": ai_summary.get("summary_text", "No summary available."),
        "params": {"from": start_date.date().isoformat(), "to": end_date.date().isoformat(), "range": "30d"}
    })
    return templates.TemplateResponse("dashboard.html", context)

@app.get("/sync/run")
async def sync_run(request: Request, company_id: int, db: Session = Depends(get_db)):
    """Triggers review sync. Handles cases where the Maps service might be missing."""
    user = get_current_user(request)
    if not user: return RedirectResponse("/login")

    if not maps_svc:
        return {"status": "error", "message": "Google Maps service is not configured."}

    company = db.query(Company).filter(Company.id == company_id).first()
    if company and company.place_id:
        try:
            new_count = await maps_svc.sync_company_reviews(db, company)
            return RedirectResponse(f"/dashboard/{company_id}?success=synced&count={new_count}")
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return RedirectResponse(f"/dashboard/{company_id}?error=sync_failed")
    
    return RedirectResponse(f"/dashboard/{company_id}?error=no_place_id")

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")

# ─────────────────────────────────────────────────────────────
# Include all routers
# ─────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(reviews.router)
app.include_router(reply.router)
app.include_router(reports.router)
app.include_router(dashboard_module.router) 
app.include_router(maps_router)
app.include_router(activity_router, prefix="/api/activity", tags=["telemetry"])
app.include_router(insights_router, prefix="/api/insights", tags=["ai"])

@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.APP_NAME}
