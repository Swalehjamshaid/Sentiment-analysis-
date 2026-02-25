# FILE: app/routes/dashboard.py
"""
Dashboard Router
Fully aligned with:
- Google API integration rule
- Front-end dashboard.html variable requirements
- Roles, health, charts, KPIs, summaries
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session

from app.db import get_db
from app import models

# --- Services ---
from app.services.rbac import get_current_user
from app.services import ai_insights as ai_svc
from app.services import metrics as metrics_svc

# Google API centralization (RULE APPLIED)
from app.services.google_api import GoogleAPIService, get_google_api_service

# Import common_context from main to ensure base template variables exist
from app.main import common_context

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


# ===========================
# INTERNAL HELPERS
# ===========================

def _parse_date(d: Optional[str]) -> Optional[datetime]:
    if not d:
        return None
    try:
        dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _quick_range(range_key: Optional[str]):
    if not range_key:
        return None, None

    now = datetime.now(timezone.utc)
    r = range_key.lower()

    if r == "7d":  return now - timedelta(days=7), now
    if r == "30d": return now - timedelta(days=30), now
    if r == "90d": return now - timedelta(days=90), now
    if r == "qtr":
        q = (now.month - 1) // 3 + 1
        start_month = (q - 1) * 3 + 1
        start = now.replace(month=start_month, day=1, hour=0, minute=0, second=0)
        return start, now

    return None, None


# ===========================
# DASHBOARD ROUTE
# ===========================

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    company_id: Optional[int] = Query(None),
    range: Optional[str] = Query(None, pattern="^(7d|30d|90d|qtr)$"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,

    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),

    google: GoogleAPIService = Depends(get_google_api_service),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    # ─────────────────────────────────────────────────────────────
    # FIX: Explicitly cast current_user.id to int to prevent PostgreSQL 
    # 'text = integer' operator mismatch error.
    # ─────────────────────────────────────────────────────────────
    try:
        u_id = int(current_user.id)
    except (ValueError, TypeError, AttributeError):
        u_id = None

    # Fetch companies depending on user role
    if getattr(current_user, "role", None) == "admin":
        companies = db.query(models.Company).order_by(models.Company.created_at.desc()).all()
    else:
        companies = (
            db.query(models.Company)
            .filter(models.Company.owner_id == u_id)
            .order_by(models.Company.created_at.desc())
            .all()
        )

    # ─────────────────────────────────────────────────────────────
    # FIX: Provide complete context for empty states to prevent Template Errors
    # ─────────────────────────────────────────────────────────────
    if not companies:
        ctx = common_context(request)
        ctx.update({
            "companies": [],
            "active_company": None,
            "params": {"from": "", "to": "", "range": ""},
            "kpi": {},
            "charts": {},
            "reviews": [],
            "summary": "No companies associated with your account yet.",
            "api_health": [],
            "alerts": [],
            "roles": []
        })
        return templates.TemplateResponse("dashboard.html", ctx)

    # Active company selection logic
    active = None
    if company_id:
        active = next((c for c in companies if c.id == company_id), None)
    if not active:
        active = companies[0]
        company_id = active.id

    # Date range processing
    sdt, edt = _quick_range(range)
    if from_: sdt = _parse_date(from_)
    if to:    edt = _parse_date(to)
    if sdt and not sdt.tzinfo: sdt = sdt.replace(tzinfo=timezone.utc)
    if edt and not edt.tzinfo: edt = edt.replace(tzinfo=timezone.utc)

    params = {
        "from": from_ or (sdt.date().isoformat() if sdt else ""),
        "to": to or (edt.date().isoformat() if edt else ""),
        "range": range or ""
    }

    # Fetch reviews
    q = db.query(models.Review).filter(models.Review.company_id == company_id)
    if sdt: q = q.filter(models.Review.review_date >= sdt)
    if edt: q = q.filter(models.Review.review_date <= edt)
    reviews = q.order_by(models.Review.review_date.desc()).all()

    # Attach latest replies
    reply_map: Dict[int, models.Reply] = {}
    reply_rows = (
        db.query(models.Reply)
        .join(models.Review, models.Reply.review_id == models.Review.id)
        .filter(models.Review.company_id == company_id)
        .all()
    )
    for rp in reply_rows:
        if rp.review_id not in reply_map:
            reply_map[rp.review_id] = rp
        else:
            if (rp.replied_at) > (reply_map[rp.review_id].replied_at):
                reply_map[rp.review_id] = rp

    review_vm = []
    for r in reviews:
        latest = reply_map.get(r.id)
        review_vm.append(SimpleNamespace(
            id=r.id,
            review_date=r.review_date,
            reviewer_name=r.reviewer_name,
            rating=r.rating,
            sentiment_category=r.sentiment_category,
            sentiment_score=r.sentiment_score,
            sentiment_confidence=r.sentiment_confidence,
            emotion_label=r.emotion_label,
            is_spam_suspected=r.is_spam_suspected,
            aspect_summary=r.aspect_summary,
            topics=r.topics,
            keywords=r.keywords,
            language=r.language,
            text=r.text,
            ai_suggested_reply=(latest.text if latest else None),
            user_reply=(latest.text if latest else None)
        ))

    # KPI and charts
    kpi = metrics_svc.build_kpi_for_dashboard(db, company_id, sdt, edt)
    charts = metrics_svc.build_dashboard_charts(db, company_id, sdt, edt)

    # AI summary
    ai_summary = ai_svc.analyze_reviews(reviews, active, sdt, edt)
    summary_text = ai_summary.get("summary_text") or "No summary available."

    # API health
    health_data = (
        db.query(models.ApiHealthCheck)
        .filter(models.ApiHealthCheck.company_id == company_id)
        .order_by(models.ApiHealthCheck.last_checked_at.desc())
        .all()
    )
    api_health = [{"provider": h.provider, "status": h.status} for h in health_data] if health_data else []

    # Alerts
    alert_rows = (
        db.query(models.Alert)
        .filter(models.Alert.company_id == company_id)
        .order_by(models.Alert.triggered_at.desc())
        .limit(10)
        .all()
    )

    # Roles
    try:
        from app.services.rbac import get_user_roles_for_company
        roles_list = get_user_roles_for_company(db, current_user, company_id)
    except Exception:
        roles_list = []

    # Merge successful dashboard data with common context
    final_ctx = common_context(request)
    final_ctx.update({
        "companies": companies,
        "active_company": active,
        "params": params,
        "kpi": kpi,
        "charts": charts,
        "reviews": review_vm,
        "summary": summary_text,
        "api_health": api_health,
        "roles": roles_list,
        "alerts": alert_rows,
    })

    return templates.TemplateResponse("dashboard.html", final_ctx)
