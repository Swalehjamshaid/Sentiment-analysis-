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
from .routes import auth, companies, reviews, reply, reports, dashboard as dashboard_module
from .routes.maps_routes import router as maps_router
from .routes.activity import router as activity_router
from .routes.insights import router as insights_router

# Import Services
from .services import metrics as metrics_svc
from .services import ai_insights as ai_svc

try:
    from .services import google_maps as maps_svc
except ImportError:
    maps_svc = None

# ─────────────────────────────────────────────────────────────
# Settings & Paths
# ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("review_saas")

class Settings:
    APP_NAME: str = "ReviewSaaS"
    FORCE_HTTPS: bool = bool(int(os.getenv("FORCE_HTTPS", "0")))
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "prod_secret_123")

settings = Settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(drop_existing=os.getenv("DROP_ALL_TABLES") == "1")
    yield

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# ─────────────────────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────────────────────
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─────────────────────────────────────────────────────────────
# Templates & Jinja Config
# ─────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

def format_date(value, fmt="%b %d, %Y"):
    if value is None: return ""
    mapping = {'Y-m-d': '%Y-%m-%d', 'd-m-Y': '%d-%m-%Y', 'H:i': '%H:%M'}
    fmt = mapping.get(fmt, fmt)
    if isinstance(value, str):
        try: value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except: return value
    return value.strftime(fmt)

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
templates.env.globals["now"] = lambda: datetime.now(timezone.utc)
templates.env.globals["csrf_token"] = _csrf_token

# ─────────────────────────────────────────────────────────────
# Context Helper
# ─────────────────────────────────────────────────────────────
def get_safe_context(request: Request, current_user=None) -> dict:
    ctx = common_context(request)
    mock_obj = {"id": 0, "name": "Select Company", "industry": "N/A"}
    ctx.update({
        "current_user": current_user, "companies": [], "selected_company": mock_obj,
        "active_company": mock_obj, "params": {"from": "", "to": ""},
        "kpi": {"avg_rating": 0, "review_count": 0, "sentiment_score": 0, "pos":0, "neu":0, "neg":0},
        "charts": {"labels": [], "sentiment": [], "rating": [], "dist": {}},
        "reviews": [], "summary": "Waiting for data...", "api_health": [], "alerts": [], "roles": []
    })
    return ctx

# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if user and user.companies:
        return RedirectResponse(f"/dashboard/{user.companies[0].id}")
    return templates.TemplateResponse("dashboard.html", get_safe_context(request, user))

@app.post("/login")
async def login_post(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    result = await auth.login_post(request, email, password, db)
    if isinstance(result, RedirectResponse): return result
    if result and hasattr(result, 'id'):
        request.session["user_id"] = result.id
        comp = db.query(Company).filter(Company.owner_id == result.id).first()
        return RedirectResponse(f"/dashboard/{comp.id}" if comp else "/", status_code=302)
    return RedirectResponse("/login?error=1")

@app.get("/dashboard/{company_id}", response_class=HTMLResponse)
async def dashboard_view(request: Request, company_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user: return RedirectResponse("/")
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company: return RedirectResponse("/")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    
    ctx = common_context(request)
    ctx.update({
        "current_user": user, "selected_company": company, "active_company": company,
        "companies": db.query(Company).filter(Company.owner_id == user.id).all(),
        "kpi": metrics_svc.build_kpi_for_dashboard(db, company_id, start, end),
        "charts": metrics_svc.build_dashboard_charts(db, company_id, start, end),
        "reviews": db.query(Review).filter(Review.company_id == company_id).limit(10).all(),
        "summary": "Data loaded.", "params": {"from": start.date().isoformat(), "to": end.date().isoformat()}
    })
    return templates.TemplateResponse("dashboard.html", ctx)

@app.get("/sync/run")
async def sync_run(request: Request, company_id: int, db: Session = Depends(get_db)):
    if not maps_svc: return {"error": "Service missing"}
    company = db.query(Company).filter(Company.id == company_id).first()
    if company and company.place_id:
        await maps_svc.sync_company_reviews(db, company)
    return RedirectResponse(f"/dashboard/{company_id}")

app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(reviews.router)
app.include_router(dashboard_module.router)
