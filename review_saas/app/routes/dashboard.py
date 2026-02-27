# FILE: review_saas/app/routes/dashbord.py
"""
REST API for the dashboard (front-end: dasbord.html)
- Auth via get_current_user
- Safe defaults (no crashes when data is missing)
- Outputs are stable and front-end-friendly
- Google API ENABLED:
    * Health check: GET /api/google/health
    * Sync trigger: POST /api/google/sync  (uses services.ingestion.sync_google_reviews)
    * Optional auto-sync via ?sync=true on data endpoints
"""

from __future__ import annotations

import io
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple

from fastapi import APIRouter, Depends, Request, Query, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db import get_db
from app.models import Company, Review, User
from app.services.rbac import get_current_user

# Prefer your ingestion service (Google Places API integration)
try:
    from app.services.ingestion import sync_google_reviews
except Exception:
    sync_google_reviews = None  # soft fallback if module not present

logger = logging.getLogger("review_saas.dashbord")
router = APIRouter(prefix="/api", tags=["dashboard-api"])

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 or YYYY-MM-DD; returns tz-aware UTC or None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        try:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None

def _quick_range(range_key: Optional[str]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Quick ranges: 7d, 30d, 90d, qtr"""
    if not range_key:
        return None, None
    now = datetime.now(timezone.utc)
    key = range_key.lower()
    if key == "7d":
        return now - timedelta(days=7), now
    if key == "30d":
        return now - timedelta(days=30), now
    if key == "90d":
        return now - timedelta(days=90), now
    if key == "qtr":
        quarter = (now.month - 1) // 3 + 1
        start_month = (quarter - 1) * 3 + 1
        start = now.replace(month=start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now
    return None, None

def _resolve_company(db: Session, user: User, company_id: Optional[int]) -> Optional[Company]:
    """Pick active company; mirrors your SSR dashboard selection logic."""
    q = db.query(Company)
    if getattr(user, "role", None) != "admin":
        q = q.filter(Company.owner_id == user.id)
    companies = q.order_by(Company.created_at.desc()).all()
    if not companies:
        return None
    if company_id:
        for c in companies:
            if c.id == company_id:
                return c
    return companies[0]

def _review_window_query(
    db: Session, company_id: int, start: Optional[datetime], end: Optional[datetime]
):
    q = db.query(Review).filter(Review.company_id == company_id)
    if start:
        q = q.filter(Review.review_date >= start)
    if end:
        q = q.filter(Review.review_date <= end)
    return q

def _maybe_auto_sync(db: Session, company: Company) -> Dict[str, Any]:
    """
    Optionally called when ?sync=true is passed to KPI/series/mix/activity endpoints.
    Uses services.ingestion.sync_google_reviews to fetch latest reviews from Google Places.
    """
    if sync_google_reviews is None:
        return {"status": "unavailable", "reason": "ingestion module not found"}

    google_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not google_key:
        return {"status": "unavailable", "reason": "GOOGLE_PLACES_API_KEY missing"}

    if not getattr(company, "place_id", None):
        return {"status": "skipped", "reason": "company has no place_id"}

    try:
        summary = sync_google_reviews(db=db, company_id=company.id)
        return {"status": "ok", "summary": summary}
    except Exception as e:
        logger.exception("Auto sync failed for company_id=%s", company.id)
        return {"status": "error", "error": str(e)}

# ─────────────────────────────────────────────────────────────
# GOOGLE API: Health & Manual Sync
# ─────────────────────────────────────────────────────────────

@router.get("/google/health")
def google_health(
    request: Request,
    company_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reports Google integration readiness for the active company:
      - GOOGLE_PLACES_API_KEY presence
      - company.place_id presence
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    company = _resolve_company(db, current_user, company_id)
    if not company:
        return {"healthy": False, "status": "no_company", "details": "No accessible companies"}

    key_present = bool(os.getenv("GOOGLE_PLACES_API_KEY"))
    has_place_id = bool(getattr(company, "place_id", None))

    healthy = key_present and has_place_id and (sync_google_reviews is not None)

    return {
        "healthy": healthy,
        "status": "ok" if healthy else "not_ready",
        "details": {
            "GOOGLE_PLACES_API_KEY": "present" if key_present else "missing",
            "place_id": "present" if has_place_id else "missing",
            "ingestion_service": "available" if sync_google_reviews is not None else "missing",
            "company_id": company.id,
            "company_name": company.name,
        }
    }

@router.post("/google/sync")
def google_sync(
    request: Request,
    company_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Triggers a Google Places reviews ingestion for the active company.
    Uses services.ingestion.sync_google_reviews (server-side key).
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    company = _resolve_company(db, current_user, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="No accessible company found")

    if sync_google_reviews is None:
        raise HTTPException(status_code=503, detail="Ingestion service not available")

    if not os.getenv("GOOGLE_PLACES_API_KEY"):
        raise HTTPException(status_code=503, detail="GOOGLE_PLACES_API_KEY missing")

    if not getattr(company, "place_id", None):
        raise HTTPException(status_code=400, detail="Company has no place_id")

    try:
        summary = sync_google_reviews(db=db, company_id=company.id)
        return {"status": "ok", "summary": summary, "company_id": company.id}
    except Exception as e:
        logger.exception("Manual Google sync failed for company_id=%s", company.id)
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────────────────────
# KPIs
# ─────────────────────────────────────────────────────────────

@router.get("/kpis")
def get_kpis(
    request: Request,
    company_id: Optional[int] = Query(None),
    range_key: Optional[str] = Query(None, alias="range", regex="^(7d|30d|90d|qtr)$"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    sync: bool = Query(False, description="Set true to attempt a quick Google auto-sync"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns dashboard KPIs in a front-end-compatible shape.

    Mapping to reviews domain:
      - ordersToday  → reviewsToday
      - slaPct       → response rate % (responded / total in window)
      - backlog      → unresponded reviews
      - returnsPct   → negative review rate %
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    company = _resolve_company(db, current_user, company_id)
    if not company:
        return JSONResponse({"ordersToday": 0, "slaPct": 0.0, "backlog": 0, "returnsPct": 0.0})

    # Optional auto sync
    if sync:
        _maybe_auto_sync(db, company)

    sdt, edt = _quick_range(range_key)
    if start:
        sdt = _parse_iso(start)
    if end:
        edt = _parse_iso(end)

    # Defaults: last 30d if nothing provided
    if not sdt or not edt:
        edt = datetime.now(timezone.utc)
        sdt = edt - timedelta(days=30)

    # Reviews today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = db.query(func.count(Review.id)).filter(
        Review.company_id == company.id,
        Review.review_date >= today_start
    ).scalar() or 0

    # Window stats
    window_q = _review_window_query(db, company.id, sdt, edt)
    total_in_window = window_q.count()

    responded_count = window_q.filter(Review.response_date.isnot(None)).count()
    unresponded_count = total_in_window - responded_count

    negative_count = window_q.filter(Review.sentiment_category == 'Negative').count()

    response_rate = round((responded_count / total_in_window) * 100.0, 1) if total_in_window else 0.0
    negative_rate = round((negative_count / total_in_window) * 100.0, 1) if total_in_window else 0.0

    return {
        "ordersToday": int(today_count),
        "slaPct": response_rate,
        "backlog": int(unresponded_count),
        "returnsPct": negative_rate
    }

# ─────────────────────────────────────────────────────────────
# Orders Series (mapped to reviews/day)
# ─────────────────────────────────────────────────────────────

@router.get("/orders/series")
def orders_series(
    request: Request,
    company_id: Optional[int] = Query(None),
    days: int = Query(14, ge=1, le=90),
    sync: bool = Query(False, description="Set true to attempt a quick Google auto-sync"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns labels + series for the line chart.
    Domain mapping: each data point is the count of reviews per day.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    company = _resolve_company(db, current_user, company_id)
    if not company:
        return {"labels": [], "series": []}

    # Optional auto sync
    if sync:
        _maybe_auto_sync(db, company)

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days - 1)

    # Group by day (SQL-level)
    rows = (
        db.query(
            func.date(Review.review_date).label("d"),
            func.count(Review.id).label("c")
        )
        .filter(Review.company_id == company.id)
        .filter(Review.review_date >= start)
        .group_by(func.date(Review.review_date))
        .order_by(func.date(Review.review_date))
        .all()
    )

    # Map by date for continuity
    by_day: Dict[str, int] = {str(r.d): int(r.c) for r in rows}

    labels: List[str] = []
    series: List[int] = []
    for i in range(days):
        dt = (start + timedelta(days=i)).date()
        key = str(dt)
        labels.append(dt.strftime("%b %d"))
        series.append(by_day.get(key, 0))

    return {"labels": labels, "series": series}

# ─────────────────────────────────────────────────────────────
# Category Mix (mapped to sentiment mix %)
# ─────────────────────────────────────────────────────────────

@router.get("/category-mix")
def category_mix(
    request: Request,
    company_id: Optional[int] = Query(None),
    range_key: Optional[str] = Query("30d", alias="range", regex="^(7d|30d|90d|qtr)$"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    sync: bool = Query(False, description="Set true to attempt a quick Google auto-sync"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns a doughnut chart mix.
    Mapping: sentiment distribution as % (Positive/Neutral/Negative).
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    company = _resolve_company(db, current_user, company_id)
    if not company:
        return {"labels": [], "data": []}

    # Optional auto sync
    if sync:
        _maybe_auto_sync(db, company)

    sdt, edt = _quick_range(range_key)
    if start:
        sdt = _parse_iso(start)
    if end:
        edt = _parse_iso(end)
    if not sdt or not edt:
        edt = datetime.now(timezone.utc)
        sdt = edt - timedelta(days=30)

    q = _review_window_query(db, company.id, sdt, edt)

    total = q.count()
    if total == 0:
        return {"labels": ["Positive", "Neutral", "Negative"], "data": [0, 0, 0]}

    positive = q.filter(Review.sentiment_category == "Positive").count()
    neutral = q.filter(Review.sentiment_category == "Neutral").count()
    negative = q.filter(Review.sentiment_category == "Negative").count()

    pct = lambda x: round((x / total) * 100.0, 1)
    return {
        "labels": ["Positive", "Neutral", "Negative"],
        "data": [pct(positive), pct(neutral), pct(negative)]
    }

# ─────────────────────────────────────────────────────────────
# Activity (recent rows)
# ─────────────────────────────────────────────────────────────

@router.get("/activity")
def activity(
    request: Request,
    company_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    sync: bool = Query(False, description="Set true to attempt a quick Google auto-sync"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns recent activity rows derived from reviews.
    Fields match the front-end table:
      - time   → HH:MM (UTC)
      - event  → 'New review' or 'Responded'
      - ref    → 'REV-{id}'
      - owner  → Review.source or 'System'
      - status → Success / Pending / Investigating / Delayed (mapped by sentiment/response)
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    company = _resolve_company(db, current_user, company_id)
    if not company:
        return []

    # Optional auto sync
    if sync:
        _maybe_auto_sync(db, company)

    rows: List[Review] = (
        db.query(Review)
        .filter(Review.company_id == company.id)
        .order_by(Review.review_date.desc())
        .limit(limit)
        .all()
    )

    def status_for(r: Review) -> str:
        # Map to soft statuses for UI
        if getattr(r, "response_date", None):
            return "Success"
        if getattr(r, "sentiment_category", "") == "Negative":
            return "Investigating"
        return "Pending"

    out = []
    for r in rows:
        dt = r.review_date or datetime.now(timezone.utc)
        out.append({
            "time": dt.astimezone(timezone.utc).strftime("%H:%M"),
            "event": "New review" if not getattr(r, "response_date", None) else "Responded",
            "ref": f"REV-{r.id}",
            "owner": getattr(r, "source", "System"),
            "status": status_for(r),
        })
    return out

# ─────────────────────────────────────────────────────────────
# Exports
# ─────────────────────────────────────────────────────────────

@router.get("/export/activity.csv")
def export_activity_csv(
    request: Request,
    company_id: Optional[int] = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream a CSV of recent activity derived from reviews."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    company = _resolve_company(db, current_user, company_id)
    if not company:
        # return empty CSV
        content = "time,event,ref,owner,status\n"
        return StreamingResponse(io.BytesIO(content.encode("utf-8")), media_type="text/csv")

    rows: List[Review] = (
        db.query(Review)
        .filter(Review.company_id == company.id)
        .order_by(Review.review_date.desc())
        .limit(limit)
        .all()
    )

    def status_for(r: Review) -> str:
        if getattr(r, "response_date", None):
            return "Success"
        if getattr(r, "sentiment_category", "") == "Negative":
            return "Investigating"
        return "Pending"

    buf = io.StringIO()
    buf.write("time,event,ref,owner,status\n")
    for r in rows:
        dt = (r.review_date or datetime.now(timezone.utc)).astimezone(timezone.utc)
        line = f'{dt.strftime("%Y-%m-%d %H:%M")},' \
               f'{"Responded" if getattr(r, "response_date", None) else "New review"},' \
               f'REV-{r.id},' \
               f'{getattr(r, "source", "System")},' \
               f'{status_for(r)}\n'
        buf.write(line)
    data = buf.getvalue().encode("utf-8")
    buf.close()

    return StreamingResponse(io.BytesIO(data), media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="activity.csv"'
    })

@router.get("/export/activity.xlsx")
def export_activity_xlsx(
    request: Request,
    company_id: Optional[int] = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Stream an XLSX export.
    Tries to use pandas/openpyxl; if unavailable, falls back to CSV stream.
    If you have a dedicated record.py, wire it here.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        import pandas as pd
    except Exception:
        # Fallback to CSV export
        return export_activity_csv(request, company_id, limit, db, current_user)

    company = _resolve_company(db, current_user, company_id)
    if not company:
        df = pd.DataFrame(columns=["time", "event", "ref", "owner", "status"])
    else:
        rows: List[Review] = (
            db.query(Review)
            .filter(Review.company_id == company.id)
            .order_by(Review.review_date.desc())
            .limit(limit)
            .all()
        )

        def status_for(r: Review) -> str:
            if getattr(r, "response_date", None):
                return "Success"
            if getattr(r, "sentiment_category", "") == "Negative":
                return "Investigating"
            return "Pending"

        data = []
        for r in rows:
            dt = (r.review_date or datetime.now(timezone.utc)).astimezone(timezone.utc)
            data.append({
                "time": dt.strftime("%Y-%m-%d %H:%M"),
                "event": "Responded" if getattr(r, "response_date", None) else "New review",
                "ref": f"REV-{r.id}",
                "owner": getattr(r, "source", "System"),
                "status": status_for(r),
            })
        df = pd.DataFrame(data)

    # Write to memory
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Activity", index=False)
    out.seek(0)

    return StreamingResponse(out, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="activity.xlsx"'})
