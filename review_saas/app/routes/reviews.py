# FILE: app/routes/reviews.py

from __future__ import annotations

import os
import logging
from typing import Optional, Dict, List
from datetime import datetime, timedelta, timezone

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..db import get_db
from ..models import Company, Review
from ..services.analysis import dashboard_payload
from ..services.ai_insights import classify_sentiment

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

# ─────────────────────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────────────────────
logger = logging.getLogger("reviews")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
API_TOKEN = os.getenv("API_TOKEN")
REVIEWS_SCAN_LIMIT = int(os.getenv("REVIEWS_SCAN_LIMIT", "8000"))
_G_TIMEOUT = (5, 15)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _parse_date_param(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.strptime(s, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            dt = datetime.fromisoformat(s)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def _normalize_review_date(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────
# Google Places Search
# ─────────────────────────────────────────────────────────────
@router.get("/google/places")
def google_places_search(
    q: str = Query(..., min_length=2),
    limit: int = Query(5, ge=1, le=10),
):
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")

    try:
        url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        params = {
            "input": q,
            "inputtype": "textquery",
            "fields": "place_id,name,formatted_address",
            "key": GOOGLE_PLACES_API_KEY,
        }

        resp = requests.get(url, params=params, timeout=_G_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()

        status = payload.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            logger.warning(f"Google Places error: {status}")
            raise HTTPException(502, f"Google status: {status}")

        candidates = (payload.get("candidates") or [])[:limit]

        return {
            "ok": True,
            "items": [
                {
                    "place_id": c.get("place_id"),
                    "name": c.get("name"),
                    "formatted_address": c.get("formatted_address"),
                }
                for c in candidates
            ],
        }

    except requests.RequestException as e:
        logger.error(f"Google Places request failed: {e}")
        raise HTTPException(502, "External API error")


# ─────────────────────────────────────────────────────────────
# Dashboard Summary
# ─────────────────────────────────────────────────────────────
@router.get("/summary/{company_id}")
def reviews_summary(
    company_id: int,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    include_aspects: bool = Query(True),
    db: Session = Depends(get_db),
):
    return dashboard_payload(
        db=db,
        company_id=company_id,
        start=start,
        end=end,
        top_keywords_n=20,
        alerts_window_days=14,
        revenue_months_back=6,
    )


# ─────────────────────────────────────────────────────────────
# Paginated Review List
# ─────────────────────────────────────────────────────────────
@router.get("/list/{company_id}")
def list_reviews(
    company_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    rating: Optional[int] = Query(None, ge=1, le=5),
    q: Optional[str] = Query(None, min_length=2),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    query = db.query(Review).filter(Review.company_id == company_id)

    start_dt = _parse_date_param(start)
    end_dt = _parse_date_param(end)

    if start_dt:
        query = query.filter(Review.review_date >= start_dt)
    if end_dt:
        query = query.filter(Review.review_date <= end_dt + timedelta(days=1))

    if rating is not None:
        query = query.filter(Review.rating == rating)

    if q:
        term = f"%{q.strip()}%"
        filters = [Review.text.ilike(term)]
        if hasattr(Review, "reviewer_name"):
            filters.append(Review.reviewer_name.ilike(term))
        query = query.filter(or_(*filters))

    total = query.count()

    if hasattr(Review, "review_date"):
        query = query.order_by(
            Review.review_date.asc() if order == "asc" else Review.review_date.desc()
        )

    items = query.offset((page - 1) * limit).limit(limit).all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [
            {
                "id": r.id,
                "rating": r.rating,
                "text": r.text,
                "reviewer_name": getattr(r, "reviewer_name", None),
                "review_date": (
                    _normalize_review_date(r.review_date) or datetime.now(timezone.utc)
                ).isoformat(),
                "sentiment_category": r.sentiment_category,
                "sentiment_score": r.sentiment_score,
                "keywords": r.keywords,
                "language": r.language,
            }
            for r in items
        ],
    }


# ─────────────────────────────────────────────────────────────
# Sync Reviews
# ─────────────────────────────────────────────────────────────
@router.post("/sync/{company_id}")
def reviews_sync(
    company_id: int,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    max_reviews: int = Query(60, ge=1, le=200),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    if API_TOKEN:
        token = (x_api_key or "").strip()
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if token != API_TOKEN:
            raise HTTPException(401, "Invalid API token")

    try:
        from ..services.ingestion import fetch_and_save_reviews_places
    except ImportError:
        raise HTTPException(
            501,
            "Ingestion service missing. Provide fetch_and_save_reviews_places().",
        )

    try:
        added = fetch_and_save_reviews_places(
            company,
            db,
            max_reviews=min(max_reviews, REVIEWS_SCAN_LIMIT),
        )
        return {"ok": True, "added": int(added or 0)}

    except Exception as e:
        logger.error(f"Sync failed for company {company_id}: {e}")
        raise HTTPException(502, "Review ingestion failed")


# ─────────────────────────────────────────────────────────────
# Diagnostics
# ─────────────────────────────────────────────────────────────
@router.get("/diagnostics")
def reviews_diagnostics():
    return {
        "google_places_key_present": bool(GOOGLE_PLACES_API_KEY),
        "api_token_configured": bool(API_TOKEN),
        "reviews_scan_limit": REVIEWS_SCAN_LIMIT,
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
    }
