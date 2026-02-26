# filename: review_saas/app/main.py
import os
import logging
import secrets
from pathlib import Path
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from markupsafe import Markup
from jinja2 import pass_context

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

# Local imports
from .db import init_db, get_db
from .models import Company, User, Review
from .services.rbac import get_current_user
from .context import common_context

# Routers
from .routes import auth, companies, reviews, reply, reports, dashboard as dashboard_module
from .routes.maps_routes import router as maps_router
from .routes.activity import router as activity_router
from .routes.insights import router as insights_router

# Services
from .services import metrics as metrics_svc
from .services import ai_insights as ai_svc

# Google Maps sync
from .services.google_maps import sync_company_reviews

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
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

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
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET,
    session_cookie="session",
    max_age=3600 * 24 * 7,  # 7 days
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
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────
# Templates & Jinja Environment
# ─────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
# make templates available to routers (auth.py uses request.app.state.templates)
app.state.templates = templates

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

def format_date(value, fmt: str = "%b %d, %Y"):
    if value is None:
        return ""
    mapping = {"Y-m-d": "%Y-%m-%d", "d-m-Y": "%d-%m-%Y", "H:i": "%H:%M", "M d, Y": "%b %d, %Y"}
    fmt = mapping.get(fmt, fmt)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return value
    try:
        return value.strftime(fmt)
    except Exception:
        return str(value)

@pass_context
def _csrf_token(context: dict, **kwargs):
    request: Optional[Request] = kwargs.get("request") or context.get("request")
    if not request:
        return Markup("")
    token = request.session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["_csrf"] = token
    return Markup(f'<input type="hidden" name="csrf_token" value="{token}">')

templates.env.filters["date"] = format_date
templates.env.globals["now"] = lambda: datetime.now(timezone.utc)
templates.env.globals["csrf_token"] = _csrf_token

# ─────────────────────────────────────────────────────────────
# Helper: Safe Context + Flash
# ─────────────────────────────────────────────────────────────
def get_safe_context(request: Request, current_user=None) -> Dict[str, Any]:
    ctx = common_context(request)
    mock_company = {"id": 0, "name": "No Company Selected", "industry": "N/A"}
    ctx.update(
        {
            "current_user": current_user,
            "companies": [],
            "selected_company": mock_company,
            "active_company": mock_company,
            "params": {"from": "", "to": "", "range": ""},
            "kpi": {"avg_rating": 0, "avg_sentiment": 0, "review_count": 0, "review_growth": "0%"},
            "charts": {
                "labels": [],
                "sentiment": [],
                "rating": [],
                "dist": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
                "correlation": [],
                "benchmark": {"labels": [], "series": []},
            },
            "reviews": [],
            "summary": "Sync or log in to see data.",
            "api_health": [],
            "alerts": [],
            "roles": [],
            "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
            "app_name": settings.APP_NAME,
        }
    )
    ctx.setdefault("request", request)
    return ctx

def _pop_flash(request: Request, key: str) -> Optional[str]:
    val = request.session.get(key)
    if val:
        try:
            del request.session[key]
        except KeyError:
            pass
    return val

# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    """
    FIRST PAGE: render base.html with modals for Register/Login/About.
    """
    user = get_current_user(request)

    context = get_safe_context(request, user)
    # deliver session flashes to template (one-time)
    context["flash_error"] = _pop_flash(request, "flash_error")
    context["flash_success"] = _pop_flash(request, "flash_success")
    context.setdefault("request", request)
    return templates.TemplateResponse("base.html", context)

@app.get("/login")
async def login_view_redirect_to_home(request: Request):
    """
    We use the base page's login modal; just open it.
    """
    return RedirectResponse("/?show=login", status_code=302)

@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Verify login via auth.login_post(); on success set session and redirect to dashboard.
    """
    # Delegate credential check to routes/auth.py
    result = await auth.login_post(request, email, password, db)
    if not result:
        request.session["flash_error"] = "Invalid email or password."
        return RedirectResponse("/?show=login", status_code=302)

    user = result
    request.session["user_id"] = user.id

    # Redirect to first company dashboard (if exists) else generic dashboard
    first_comp: Optional[Company] = (
        db.query(Company).filter(Company.owner_id == user.id).first()
    )
    if first_comp:
        return RedirectResponse(f"/dashboard/{first_comp.id}", status_code=302)
    return RedirectResponse("/dashboard", status_code=302)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_fallback(request: Request, db: Session = Depends(get_db)):
    """
    Generic dashboard shell when the user has no companies yet.
    """
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/?show=login", status_code=302)

    context = get_safe_context(request, user)
    context.setdefault("request", request)
    return templates.TemplateResponse("dashboard.html", context)

@app.get("/dashboard/{company_id}", response_class=HTMLResponse)
async def dashboard_view(request: Request, company_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/?show=login", status_code=302)

    company: Optional[Company] = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return RedirectResponse("/dashboard", status_code=302)

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=30)

    kpi = metrics_svc.build_kpi_for_dashboard(db, company_id, start_date, end_date)
    charts = metrics_svc.build_dashboard_charts(db, company_id, start_date, end_date)

    reviews_list = (
        db.query(Review)
        .filter(Review.company_id == company_id)
        .order_by(Review.review_date.desc())
        .limit(50)
        .all()
    )

    ai_summary: Dict[str, Any] = {}
    try:
        ai_summary = ai_svc.analyze_reviews(reviews_list, company, start_date, end_date) or {}
    except Exception as e:
        logger.exception("AI summary failed: %s", e)
        ai_summary = {"summary_text": "AI analysis unavailable at this time."}

    context = common_context(request)
    context.update(
        {
            "current_user": user,
            "selected_company": company,
            "active_company": company,
            "companies": db.query(Company).filter(Company.owner_id == user.id).all(),
            "kpi": kpi,
            "charts": charts,
            "reviews": reviews_list,
            "summary": ai_summary.get("summary_text", "No summary available."),
            "params": {
                "from": start_date.date().isoformat(),
                "to": end_date.date().isoformat(),
                "range": "30d",
            },
            "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
            "app_name": settings.APP_NAME,
        }
    )
    context.setdefault("request", request)
    return templates.TemplateResponse("dashboard.html", context)

@app.get("/sync/run")
async def sync_reviews(request: Request, company_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/?show=login", status_code=302)

    company: Optional[Company] = db.query(Company).filter(Company.id == company_id).first()
    if not company or not getattr(company, "place_id", None):
        return RedirectResponse(f"/dashboard/{company_id}?error=no_place_id", status_code=302)

    try:
        new_count = await sync_company_reviews(db, company)
        return RedirectResponse(f"/dashboard/{company_id}?success=synced&count={new_count}", status_code=302)
    except Exception as e:
        logger.exception("Sync failed: %s", e)
        return RedirectResponse(f"/dashboard/{company_id}?error=sync_failed", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")

# Include routers
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
