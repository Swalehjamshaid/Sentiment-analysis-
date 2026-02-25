# FILE: app/routes/dashboard.py
"""
Dashboard Router
- Railway-safe Google API integration
- Prevents 500 errors when credentials are missing
- Fully typed, clean, and bug-fixed
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
from types import SimpleNamespace
from pathlib import Path
import os
import logging

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app import models
from app.services.rbac import get_current_user
from app.services import ai_insights as ai_svc
from app.services import metrics as metrics_svc
from app.services.google_api import get_google_api_service
from app.context import common_context

logger = logging.getLogger("review_saas.dashboard")

# ─────────────────────────────────────────────────────────────
# TEMPLATE CONFIG (RAILWAY-SAFE)
# ─────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
templates_dir = BASE_DIR / "templates"
if not templates_dir.exists():
    templates_dir = BASE_DIR / "app" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

router = APIRouter()


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO date string safely, return UTC datetime."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception as e:
        logger.warning("Failed to parse date '%s': %s", date_str, e)
        return None


def _quick_range(range_key: Optional[str]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Quick date ranges for 7d, 30d, 90d, or current quarter."""
    if not range_key:
        return None, None
    now = datetime.now(timezone.utc)
    key = range_key.lower()

    if key == "7d":
        return now - timedelta(days=7), now
    elif key == "30d":
        return now - timedelta(days=30), now
    elif key == "90d":
        return now - timedelta(days=90), now
    elif key == "qtr":
        quarter = (now.month - 1) // 3 + 1
        start_month = (quarter - 1) * 3 + 1
        start = now.replace(month=start_month, day=1, hour=0, minute=0, second=0)
        return start, now

    return None, None


# ─────────────────────────────────────────────────────────────
# DASHBOARD ROUTE
# ─────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    company_id: Optional[int] = Query(None),
    range_key: Optional[str] = Query(None, alias="range", pattern="^(7d|30d|90d|qtr)$"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None, alias="to"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Railway-safe dashboard page."""
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    # ─────────────────────────────────────────────────────────
    # LOAD COMPANIES
    # ─────────────────────────────────────────────────────────

    if getattr(current_user, "role", None) == "admin":
        companies: List[models.Company] = (
            db.query(models.Company).order_by(models.Company.created_at.desc()).all()
        )
    else:
        companies: List[models.Company] = (
            db.query(models.Company)
            .filter(models.Company.owner_id == current_user.id)
            .order_by(models.Company.created_at.desc())
            .all()
        )

    if not companies:
        context = common_context(request)
        context.update({
            "companies": [],
            "active_company": None,
            "kpi": {},
            "charts": {},
            "reviews": [],
            "summary": "Add a company to begin.",
            "api_health": [{"provider": "google", "status": "not_configured"}],
            "alerts": [],
            "roles": [],
        })
        return templates.TemplateResponse("dashboard.html", context)

    # Active company
    active = next((c for c in companies if c.id == company_id), companies[0])
    company_id = active.id

    # ─────────────────────────────────────────────────────────
    # DATE RANGE
    # ─────────────────────────────────────────────────────────

    sdt, edt = _quick_range(range_key)
    if from_:
        sdt = _parse_date(from_)
    if to:
        edt = _parse_date(to)

    # ─────────────────────────────────────────────────────────
    # GOOGLE API (RAILWAY-SAFE)
    # ─────────────────────────────────────────────────────────

    google_service = None
    google_status = "not_configured"
    try:
        creds_path = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_path:
            google_service = get_google_api_service()
            google_status = "connected"
        else:
            google_status = "missing_credentials"
    except Exception as e:
        logger.warning("Google API initialization failed: %s", e)
        google_status = "error"

    # ─────────────────────────────────────────────────────────
    # REVIEWS
    # ─────────────────────────────────────────────────────────

    query = db.query(models.Review).filter(models.Review.company_id == company_id)
    if sdt:
        query = query.filter(models.Review.review_date >= sdt)
    if edt:
        query = query.filter(models.Review.review_date <= edt)
    reviews = query.order_by(models.Review.review_date.desc()).all()

    review_vm = [
        SimpleNamespace(
            id=r.id,
            review_date=r.review_date,
            reviewer_name=r.reviewer_name,
            rating=r.rating,
            sentiment_category=r.sentiment_category,
            sentiment_score=r.sentiment_score,
            text=r.text,
        )
        for r in reviews
    ]

    # ─────────────────────────────────────────────────────────
    # METRICS + AI INSIGHTS
    # ─────────────────────────────────────────────────────────

    kpi = metrics_svc.build_kpi_for_dashboard(db, company_id, sdt, edt)
    charts = metrics_svc.build_dashboard_charts(db, company_id, sdt, edt)

    try:
        ai_summary = ai_svc.analyze_reviews(reviews, active, sdt, edt)
        summary_text = ai_summary.get("summary_text", "AI summary unavailable.")
    except Exception as e:
        logger.warning("AI analysis failed: %s", e)
        summary_text = "AI summary unavailable."

    # ─────────────────────────────────────────────────────────
    # FINAL CONTEXT
    # ─────────────────────────────────────────────────────────

    context = common_context(request)
    context.update({
        "companies": companies,
        "active_company": active,
        "kpi": kpi,
        "charts": charts,
        "reviews": review_vm,
        "summary": summary_text,
        "api_health": [{"provider": "google", "status": google_status}],
        "alerts": [],
        "roles": [],
    })

    return templates.TemplateResponse("dashboard.html", context)
