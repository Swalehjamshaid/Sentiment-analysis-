# FILE: app/routes/dashboard.py
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, Review, Reply, Alert, ApiHealthCheck, UserCompanyRole
from app.services.rbac import get_current_user
from app.services import metrics as metrics_svc
from app.services import ai_insights as ai_svc

try:
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
except Exception:
    templates = None

router = APIRouter()


def _parse_range_to_window(range_key: Optional[str]) -> (Optional[datetime], Optional[datetime]):
    """Maps quick ‘range’ keys to (start, end) in UTC."""
    now = datetime.now(timezone.utc)
    if not range_key:
        return None, None
    rk = range_key.lower()
    if rk == "7d":
        return now - timedelta(days=7), now
    if rk == "30d":
        return now - timedelta(days=30), now
    if rk == "90d":
        return now - timedelta(days=90), now
    if rk in ("qtr", "quarter"):
        # current quarter start
        m = (now.month - 1) // 3 * 3 + 1
        start = now.replace(month=m, day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now
    return None, None


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    company_id: Optional[int] = Query(None),
    range: Optional[str] = Query(None, regex="^(7d|30d|90d|qtr)$"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Renders dashboard.html with ALL variables the template expects:
    companies, active_company, params, kpi, charts, reviews, summary, alerts, roles, api_health.
    """
    # Require auth
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    # Companies visible to user (admin sees all, others see owned)
    role = getattr(current_user, "role", None) or "user"
    if role == "admin":
        companies_q = db.query(Company)
    else:
        # If you later add UserCompanyRole mapping, extend here
        companies_q = db.query(Company).filter(Company.owner_id == current_user.id)

    companies = companies_q.order_by(Company.created_at.desc()).all()

    if not companies:
        # Still render page with empty state
        context = {
            "request": request,
            "companies": [],
            "active_company": None,
            "params": {"from": from_ or "", "to": to or ""},
            "kpi": {},
            "charts": {"labels": [], "sentiment": [], "rating": [], "dist": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}, "correlation": [], "benchmark": {"labels": [], "series": []}},
            "reviews": [],
            "summary": "No companies yet. Add a company to begin.",
            "alerts": [],
            "roles": [],
            "api_health": [],
        }
        if templates:
            return templates.TemplateResponse("dashboard.html", context)
        return HTMLResponse("No companies configured.", status_code=200)

    # Active company
    active_company = None
    if company_id:
        active_company = next((c for c in companies if c.id == company_id), None)
    if not active_company:
        active_company = companies[0]

    # Date window
    sdt, edt = _parse_range_to_window(range)
    if from_:
        try:
            sdt = datetime.fromisoformat(from_.replace("Z", "+00:00"))
            if not sdt.tzinfo:
                sdt = sdt.replace(tzinfo=timezone.utc)
        except Exception:
            sdt = None
    if to:
        try:
            edt = datetime.fromisoformat(to.replace("Z", "+00:00"))
            if not edt.tzinfo:
                edt = edt.replace(tzinfo=timezone.utc)
        except Exception:
            edt = None

    # Reviews for table (limit to recent 200 for UI performance)
    q = db.query(Review).filter(Review.company_id == active_company.id)
    if sdt:
        q = q.filter(Review.review_date >= sdt)
    if edt:
        q = q.filter(Review.review_date <= edt)
    reviews: List[Review] = q.order_by(Review.review_date.desc()).limit(200).all()

    # Attach last reply text (transient) so template placeholders show something
    # and a transient 'ai_suggested_reply' if present.
    if reviews:
        # map last reply by review
        review_ids = [r.id for r in reviews]
        last_replies = (
            db.query(Reply)
            .filter(Reply.review_id.in_(review_ids))
            .order_by(Reply.review_id.asc(), Reply.suggested_at.desc())
            .all()
        )
        last_by_review: Dict[int, Reply] = {}
        for rep in last_replies:
            last_by_review.setdefault(rep.review_id, rep)
        for r in reviews:
            lr = last_by_review.get(r.id)
            setattr(r, "user_reply", getattr(lr, "edited_text", "") if lr else "")
            setattr(r, "ai_suggested_reply", getattr(lr, "suggested_text", "") if lr else "")

    # KPI & charts
    kpi = metrics_svc.build_kpis(db, active_company.id, sdt, edt)
    charts = metrics_svc.build_charts(db, active_company.id, sdt, edt)

    # Executive summary (string)
    summary_dict = ai_svc.analyze_reviews(reviews, active_company, sdt, edt) or {}
    summary_text = (
        (summary_dict.get("executive_summary") or {}).get("narrative")
        or "No summary available yet."
    )

    # Alerts (last 20)
    alerts = (
        db.query(Alert)
        .filter(Alert.company_id == active_company.id)
        .order_by(Alert.occurred_at.desc())
        .limit(20)
        .all()
    )

    # API health for card
    health = (
        db.query(ApiHealthCheck)
        .filter(ApiHealthCheck.company_id == active_company.id)
        .order_by(ApiHealthCheck.checked_at.desc())
        .limit(5)
        .all()
    )
    api_health = [{"provider": h.provider, "status": h.status, "checked_at": h.checked_at} for h in health]

    # Roles exposed to template (flatten to set of strings)
    roles = (
        db.query(UserCompanyRole.role)
        .filter(UserCompanyRole.user_id == current_user.id)
        .all()
    )
    role_set = sorted({r[0] for r in roles}) if roles else ([role] if role else [])

    params = {
        "from": sdt.date().isoformat() if sdt else "",
        "to": edt.date().isoformat() if edt else "",
        "range": range or "",
    }

    context = {
        "request": request,
        "companies": companies,
        "active_company": active_company,
        "params": params,
        "kpi": kpi,
        "charts": charts,
        "reviews": reviews,
        "summary": summary_text,
        "alerts": alerts,
        "roles": role_set,
        "api_health": api_health,
    }

    if templates:
        return templates.TemplateResponse("dashboard.html", context)
    return HTMLResponse("Templates not configured", status_code=200)
