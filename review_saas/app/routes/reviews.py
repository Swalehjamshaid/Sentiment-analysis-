# FILE: app/routes/review.py

from __future__ import annotations

import os
import time
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Company, Review

# Analytics bridges (DB + pure-Python helpers)
from ..services.analysis import (
    dashboard_payload,
    reviews_table,
)
from ..services.ai_insights import (
    classify_sentiment,
)

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

logger = logging.getLogger("reviews")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

# ------------------------------------------------------------
# Config
# ------------------------------------------------------------
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
API_TOKEN = os.getenv("API_TOKEN")  # optional: protect sync
REVIEWS_SCAN_LIMIT = int(os.getenv("REVIEWS_SCAN_LIMIT", "8000"))  # cap scan for summary fallback
_G_TIMEOUT = (5, 10)


# ------------------------------------------------------------
# Local helpers
# ------------------------------------------------------------
def _parse_date_param(s: Optional[str], *, as_end: bool = False) -> Optional[datetime]:
    """
    Parse 'YYYY-MM-DD' or ISO strings; if only date is supplied for end,
    make it inclusive of the full end day by advancing to next day (open interval).
    """
    if not s:
        return None
    try:
        dt = datetime.strptime(s, "%Y-%m-%d")
        # We keep dt as-is; route code will handle <= or < next day for inclusive end
        return dt
    except Exception:
        try:
            return datetime.fromisoformat(s)
        except Exception:
            return None


def _parse_review_date(r: Review) -> Optional[datetime]:
    dt = getattr(r, "review_date", None)
    if not dt:
        return None
    if dt.tzinfo:
        return dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────
# Legacy-compatible core analysis (kept as thin delegate)
# ─────────────────────────────────────────────────────────────
def _daily_buckets_range(reviews: List[Review], start: datetime, end: datetime) -> List[Dict]:
    """
    NOTE: Kept for compatibility with older code paths that may import this.
    Internally, dashboard endpoints prefer using `dashboard_payload` which already
    returns a daily series. This function mirrors the logic against ORM rows.
    """
    start_day = start.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    end_day = end.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)
    days_diff = (end_day.date() - start_day.date()).days + 1
    if days_diff < 1:
        return []

    buckets: Dict[str, Dict] = {}
    for i in range(days_diff):
        d = (start_day + timedelta(days=i)).date().isoformat()
        buckets[d] = {"date": d, "ratings": [], "scores": [], "counts": {"Positive": 0, "Neutral": 0, "Negative": 0}}

    for r in reviews:
        dt = _parse_review_date(r)
        if not dt or dt < start_day or dt > end_day:
            continue
        day_str = dt.date().isoformat()
        lbl = classify_sentiment(getattr(r, "rating", None))
        score = 1.0 if lbl == "Positive" else -1.0 if lbl == "Negative" else 0.0
        buckets[day_str]["ratings"].append(r.rating or 0)
        buckets[day_str]["scores"].append(score)
        buckets[day_str]["counts"][lbl] += 1

    return [
        {
            "date": d,
            "avg_rating": round(sum(b["ratings"]) / len(b["ratings"]), 2) if b["ratings"] else None,
            "sent_score": round(sum(b["scores"]) / len(b["scores"]), 3) if b["scores"] else 0.0,
            **b["counts"]
        }
        for d, b in sorted(buckets.items())
    ]


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@router.get("/google/places")
def google_places_search(
    q: str = Query(..., min_length=2),
    limit: int = Query(5, ge=1, le=10),
):
    """
    Lightweight helper: delegates to Google Find Place, then enriches details.

    NOTE: If you're already using /api/companies/autocomplete and
    /api/companies/details from companies.py, prefer those in the UI.
    This endpoint is provided for backward compatibility.
    """
    if not GOOGLE_PLACES_API_KEY:
        return {"ok": False, "reason": "Google Places API not configured"}

    try:
        # 1) Find Place
        fp_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        fp_params = {
            "input": q,
            "inputtype": "textquery",
            "fields": "place_id,name,formatted_address",
            "key": GOOGLE_PLACES_API_KEY,
        }
        fp = requests.get(fp_url, params=fp_params, timeout=_G_TIMEOUT)
        fp.raise_for_status()
        fp_data = fp.json()
        candidates = (fp_data.get("candidates") or [])[:limit]

        # 2) For each candidate, fetch details
        details_url = "https://maps.googleapis.com/maps/api/place/details/json"
        items = []
        for c in candidates:
            pid = c.get("place_id")
            detail = {}
            if pid:
                dt_params = {
                    "place_id": pid,
                    # NOTE: address_components (plural) is the valid field name
                    "fields": "name,formatted_address,address_components,geometry,website,international_phone_number,rating,user_ratings_total,url",
                    "key": GOOGLE_PLACES_API_KEY,
                }
                dt = requests.get(details_url, params=dt_params, timeout=_G_TIMEOUT)
                if dt.ok:
                    djson = dt.json().get("result", {}) or {}
                    loc = ((djson.get("geometry") or {}).get("location") or {})
                    detail = {
                        "name": djson.get("name") or c.get("name"),
                        "formatted_address": djson.get("formatted_address") or c.get("formatted_address"),
                        "rating": djson.get("rating"),
                        "user_ratings_total": djson.get("user_ratings_total"),
                        "location": {"lat": loc.get("lat"), "lng": loc.get("lng")},
                        "website": djson.get("website"),
                        "international_phone_number": djson.get("international_phone_number"),
                        "url": djson.get("url"),
                    }
            items.append({
                "place_id": pid,
                **detail
            })
        return {"ok": True, "items": items}
    except Exception as e:
        logger.warning(f"Places search failed: {e}")
        return {"ok": False, "reason": "external_api_error"}


@router.get("/summary/{company_id}")
def reviews_summary(
    company_id: int,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    include_aspects: bool = Query(True, description="Kept for compatibility; dashboard_payload includes aspects"),
    db: Session = Depends(get_db),
):
    """
    Returns the full insight payload used by dashboard.html for a given company.
    This delegates to services.analysis.dashboard_payload to stay consistent.
    """
    return dashboard_payload(
        db=db,
        company_id=company_id,
        start=start,
        end=end,
        top_keywords_n=20,
        alerts_window_days=14,
        revenue_months_back=6,
    )


@router.get("/list/{company_id}")
def list_reviews(
    company_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    rating: Optional[int] = Query(None, ge=1, le=5),
    q: Optional[str] = Query(None, min_length=2),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    order: str = Query("desc", pattern="^(asc|desc)$"),  # ← pydantic v2-compatible
    db: Session = Depends(get_db),
):
    """
    Paginated review list for the table in dashboard.html.
    - Supports: text search (q), rating filter, date range, sort by review_date asc/desc
    """
    # Base query
    query = db.query(Review).filter(Review.company_id == company_id)
    # Date filter
    start_dt = _parse_date_param(start, as_end=False)
    end_dt = _parse_date_param(end, as_end=True)
    if start_dt:
        query = query.filter(Review.review_date >= start_dt)
    if end_dt:
        # inclusive end-day
        if end_dt.hour == 0 and end_dt.minute == 0 and end_dt.second == 0:
            query = query.filter(Review.review_date < (end_dt + timedelta(days=1)))
        else:
            query = query.filter(Review.review_date <= end_dt)

    # Rating filter
    if rating is not None:
        query = query.filter(Review.rating == rating)

    # Text search across known columns
    if q:
        s = f"%{q.strip()}%"
        from sqlalchemy import or_
        filters = [Review.text.ilike(s)]
        if hasattr(Review, "reviewer_name"):
            filters.append(Review.reviewer_name.ilike(s))
        query = query.filter(or_(*filters))

    total = query.count()

    # Sort
    query = query.order_by(Review.review_date.asc() if order == "asc" else Review.review_date.desc())

    # Pagination
    items = query.offset((page - 1) * limit).limit(limit).all()

    data = [
        {
            "id": r.id,
            "rating": r.rating,
            "text": r.text,
            "reviewer_name": r.reviewer_name,
            "review_date": (_parse_review_date(r) or datetime.now(timezone.utc)).isoformat(),
            "sentiment_category": r.sentiment_category,
            "sentiment_score": r.sentiment_score,
            "keywords": r.keywords,
            "language": r.language,
        }
        for r in items
    ]
    return {"total": total, "page": page, "limit": limit, "items": data}


@router.post("/sync/{company_id}")
def reviews_sync(
    company_id: int,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    max_reviews: int = Query(60, ge=1, le=200),
):
    """
    Trigger a review sync for this company.

    Integration points:
    - If you have an ingestion function (e.g., fetch_and_save_reviews_places),
      we will call it. Otherwise, we return a friendly 501 with guidance.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    # Optional API token guard
    if API_TOKEN:
        token = (x_api_key or "").strip()
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if token != API_TOKEN:
            raise HTTPException(401, "Invalid API token")

    # Attempt dynamic import of ingestion service
    try:
        from ..services.ingestion import fetch_and_save_reviews_places  # type: ignore
    except Exception:
        raise HTTPException(
            status_code=501,
            detail="Reviews ingestion service not configured. "
                   "Provide app/services/ingestion.py with fetch_and_save_reviews_places()."
        )

    try:
        added = fetch_and_save_reviews_places(company, db, max_reviews=max_reviews)  # user’s pipeline
        return {"ok": True, "added": int(added or 0), "message": "Sync completed"}
    except Exception as e:
        logger.error(f"Sync failed for company {company_id}: {e}")
        raise HTTPException(502, f"Ingestion error: {str(e)}")


@router.get("/diagnostics")
def reviews_diagnostics():
    return {
        "google_places_key_present": bool(GOOGLE_PLACES_API_KEY),
        "api_token_configured": bool(API_TOKEN),
        "default_window_days": 180,
        "reviews_scan_limit": REVIEWS_SCAN_LIMIT,
    }
