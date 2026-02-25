# FILE: app/main.py
import os, logging, secrets
from pathlib import Path
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
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
from .routes import auth, companies, reviews, dashboard as dashboard_module
from .services import metrics as metrics_svc, ai_insights as ai_svc

try: from .services import google_maps as maps_svc
except ImportError: maps_svc = None

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- WORLD CLASS JINJA CONFIG ---
def format_date(value, fmt="%Y-%m-%d"):
    if not value: return ""
    return value.strftime(fmt)

@pass_context
def _csrf_token(context: dict):
    request = context.get("request")
    token = request.session.get("_csrf") or secrets.token_urlsafe(32)
    request.session["_csrf"] = token
    return Markup(f'<input type="hidden" name="csrf_token" value="{token}">')

templates.env.filters["date"] = format_date
templates.env.globals["csrf_token"] = _csrf_token
templates.env.globals["now"] = lambda: datetime.now(timezone.utc)

app = FastAPI(title="ReviewIQ Enterprise")
from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(SessionMiddleware, secret_key="world_class_secret_123")

# --- ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if user and user.companies:
        return RedirectResponse(f"/dashboard/{user.companies[0].id}")
    return templates.TemplateResponse("base.html", {"request": request, "current_user": user})

@app.post("/login")
async def login_post(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    result = await auth.login_post(request, email, password, db)
    if isinstance(result, RedirectResponse): return result
    if result and hasattr(result, 'id'):
        request.session["user_id"] = result.id
        comp = db.query(Company).filter_by(owner_id=result.id).first()
        return RedirectResponse(f"/dashboard/{comp.id}" if comp else "/", status_code=303)
    return RedirectResponse("/?error=1")

@app.get("/dashboard/{company_id}", response_class=HTMLResponse)
async def dashboard_view(request: Request, company_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user: return RedirectResponse("/")
    company = db.query(Company).get(company_id)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    
    ctx = common_context(request)
    ctx.update({
        "current_user": user, "active_company": company,
        "companies": db.query(Company).filter_by(owner_id=user.id).all(),
        "kpi": metrics_svc.build_kpi_for_dashboard(db, company_id, start, end),
        "charts": metrics_svc.build_dashboard_charts(db, company_id, start, end),
        "reviews": db.query(Review).filter_by(company_id=company_id).order_by(Review.review_date.desc()).all(),
        "summary": await ai_svc.get_executive_summary(company_id, db),
        "params": {"from": start.date().isoformat(), "to": end.date().isoformat()}
    })
    return templates.TemplateResponse("dashboard.html", ctx)

@app.get("/sync/run")
async def sync_run(request: Request, company_id: int, db: Session = Depends(get_db)):
    if maps_svc:
        company = db.query(Company).get(company_id)
        await maps_svc.sync_company_reviews(db, company)
    return RedirectResponse(f"/dashboard/{company_id}")

@app.post("/reviews/{review_id}/reply/suggest")
async def suggest_reply(review_id: int, db: Session = Depends(get_db)):
    review = db.query(Review).get(review_id)
    company = db.query(Company).get(review.company_id)
    review.ai_suggested_reply = await ai_svc.generate_ai_reply(review.text, review.rating, company.name)
    db.commit()
    return RedirectResponse(f"/dashboard/{review.company_id}", status_code=303)

app.include_router(auth.router)
app.include_router(companies.router)
