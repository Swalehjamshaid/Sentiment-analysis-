import os
import logging
import secrets
from pathlib import Path
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request, Form, Depends, HTTPException
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
# Service and Route imports
from .routes import auth, companies, reviews, reply, reports, dashboard as dashboard_module
from .services import metrics as metrics_svc, ai_insights as ai_svc

try:
    from .services import google_maps as maps_svc
except ImportError:
    maps_svc = None

# ─────────────────────────────────────────────────────────────
# Paths & Settings
# ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("review_saas")

# ─────────────────────────────────────────────────────────────
# Jinja Configuration
# ─────────────────────────────────────────────────────────────
def format_date(value, fmt="%b %d, %Y"):
    if not value: return ""
    mapping = {'Y-m-d': '%Y-%m-%d', 'd-m-Y': '%d-%m-%Y'}
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
# App & Middleware
# ─────────────────────────────────────────────────────────────
app = FastAPI(title="ReviewIQ Engine")
from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "super-secret"))

if (BASE_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ─────────────────────────────────────────────────────────────
# Optimized Dashboard Logic
# ─────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if user and hasattr(user, 'companies') and user.companies:
        return RedirectResponse(f"/dashboard/{user.companies[0].id}")
    
    ctx = common_context(request)
    ctx.update({"current_user": user, "companies": [], "active_company": None})
    return templates.TemplateResponse("base.html", ctx)

@app.post("/login")
async def login_post(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    result = await auth.login_post(request, email, password, db)
    if isinstance(result, RedirectResponse):
        return result
    
    if result and hasattr(result, 'id'):
        request.session["user_id"] = result.id
        first_comp = db.query(Company).filter(Company.owner_id == result.id).first()
        if first_comp:
            return RedirectResponse(f"/dashboard/{first_comp.id}", status_code=302)
    return RedirectResponse("/?error=login_failed")

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
        "current_user": user,
        "active_company": company,
        "companies": db.query(Company).filter(Company.owner_id == user.id).all(),
        "kpi": metrics_svc.build_kpi_for_dashboard(db, company_id, start, end),
        "charts": metrics_svc.build_dashboard_charts(db, company_id, start, end),
        "reviews": db.query(Review).filter(Review.company_id == company_id).order_by(Review.review_date.desc()).all(),
        "params": {"from": start.date().isoformat(), "to": end.date().isoformat()}
    })
    return templates.TemplateResponse("dashboard.html", ctx)

@app.get("/sync/run")
async def sync_run(request: Request, company_id: int, db: Session = Depends(get_db)):
    if not maps_svc: return {"error": "Google Maps Service Unavailable"}
    company = db.query(Company).filter(Company.id == company_id).first()
    if company and company.place_id:
        await maps_svc.sync_company_reviews(db, company)
    return RedirectResponse(f"/dashboard/{company_id}")

# ─────────────────────────────────────────────────────────────
# Include Routers
# ─────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(reviews.router)
app.include_router(dashboard_module.router)
