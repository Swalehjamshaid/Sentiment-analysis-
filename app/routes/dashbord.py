
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
from app.models import Company, Review
from app.services.rbac import get_current_user

try:
    from app.services.ingestion import sync_google_reviews
except Exception:
    sync_google_reviews = None

logger = logging.getLogger("review_saas.dashbord")
router = APIRouter(prefix="/api", tags=["dashboard-api"])

def _parse_iso(value: Optional[str]) -> Optional[datetime]:
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

def _resolve_company(db: Session, user, company_id: Optional[int]) -> Optional[Company]:
    q = db.query(Company)
    companies = q.order_by(Company.created_at.desc()).all()
    if not companies:
        return None
    if company_id:
        for c in companies:
            if c.id == company_id:
                return c
    return companies[0]

def _review_window_query(db: Session, company_id: int, start: Optional[datetime], end: Optional[datetime]):
    q = db.query(Review).filter(Review.company_id == company_id)
    if start:
        q = q.filter(Review.review_date >= start)
    if end:
        q = q.filter(Review.review_date <= end)
    return q

def _maybe_auto_sync(db: Session, company: Company) -> Dict[str, Any]:
    if sync_google_reviews is None:
        return {"status": "unavailable", "reason": "ingestion module not found"}
    if not os.getenv("GOOGLE_PLACES_API_KEY"):
        return {"status": "unavailable", "reason": "GOOGLE_PLACES_API_KEY missing"}
    if not getattr(company, "place_id", None):
        return {"status": "skipped", "reason": "company has no place_id"}
    try:
        summary = sync_google_reviews(db=db, company_id=company.id)
        return {"status": "ok", "summary": summary}
    except Exception as e:
        logger.exception("Auto sync failed for company_id=%s", company.id)
        return {"status": "error", "error": str(e)}

@router.get("/kpis")
def get_kpis(
    request: Request,
    company_id: Optional[int] = Query(None),
    range_key: Optional[str] = Query(None, alias="range", regex="^(7d|30d|90d|qtr)$"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    sync: bool = Query(False),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    company = _resolve_company(db, current_user, company_id)
    if not company:
        return JSONResponse({"ordersToday": 0, "slaPct": 0.0, "backlog": 0, "returnsPct": 0.0})

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

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = db.query(func.count(Review.id)).filter(
        Review.company_id == company.id, Review.review_date >= today_start
    ).scalar() or 0

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

@router.get("/orders/series")
def orders_series(
    request: Request,
    company_id: Optional[int] = Query(None),
    days: int = Query(14, ge=1, le=90),
    sync: bool = Query(False),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    company = _resolve_company(db, current_user, company_id)
    if not company:
        return {"labels": [], "series": []}

    if sync:
        _maybe_auto_sync(db, company)

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days - 1)

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

    by_day: Dict[str, int] = {str(r.d): int(r.c) for r in rows}

    labels: List[str] = []
    series: List[int] = []
    for i in range(days):
        dt = (start + timedelta(days=i)).date()
        key = str(dt)
        labels.append(dt.strftime("%b %d"))
        series.append(by_day.get(key, 0))

    return {"labels": labels, "series": series}

@router.get("/category-mix")
def category_mix(
    request: Request,
    company_id: Optional[int] = Query(None),
    range_key: Optional[str] = Query("30d", alias="range", regex="^(7d|30d|90d|qtr)$"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    sync: bool = Query(False),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    company = _resolve_company(db, current_user, company_id)
    if not company:
        return {"labels": [], "data": []}

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

@router.get("/activity")
def activity(
    request: Request,
    company_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    sync: bool = Query(False),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    company = _resolve_company(db, current_user, company_id)
    if not company:
        return []

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
        if getattr(r, "response_date", None):
            return "Success"
        if (r.sentiment_category or "") == "Negative":
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

@router.get("/export/activity.csv")
def export_activity_csv(
    request: Request,
    company_id: Optional[int] = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    company = _resolve_company(db, current_user, company_id)
    if not company:
        content = "time,event,ref,owner,status
"
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
        if (r.sentiment_category or "") == "Negative":
            return "Investigating"
        return "Pending"

    buf = io.StringIO()
    buf.write("time,event,ref,owner,status
")
    for r in rows:
        dt = (r.review_date or datetime.now(timezone.utc)).astimezone(timezone.utc)
        line = f'{dt.strftime("%Y-%m-%d %H:%M")},'                f'{"Responded" if getattr(r, "response_date", None) else "New review"},'                f'REV-{r.id},'                f'{getattr(r, "source", "System")},'                f'{status_for(r)}
'
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
    current_user = Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        import pandas as pd
    except Exception:
        return export_activity_csv(request, company_id, limit, db, current_user)

    company = _resolve_company(db, current_user, company_id)
    if not company:
        import pandas as pd  # type: ignore
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
            if (r.sentiment_category or "") == "Negative":
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

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Activity", index=False)
    out.seek(0)

    return StreamingResponse(out, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="activity.xlsx"'})
