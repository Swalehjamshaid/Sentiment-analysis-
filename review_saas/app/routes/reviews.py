# FILE: app/routes/reviews.py
from __future__ import annotations

import os
import sys
import time
import logging
from typing import Optional, Dict, List, Any, Tuple, Literal
from datetime import datetime, timedelta, timezone

import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from fastapi import (
    APIRouter, Depends, HTTPException, Query, Header, Path, status
)
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..db import get_db
from ..models import Company, Review
from ..services.analysis import dashboard_payload

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
# Config (env → fallback to provided keys)
# ─────────────────────────────────────────────────────────────
GOOGLE_MAPS_API_KEY: str = os.getenv(
    "GOOGLE_MAPS_API_KEY",
    "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg",
)
GOOGLE_BUSINESS_API_KEY: str = os.getenv(
    "GOOGLE_BUSINESS_API_KEY",
    "AIzaSyDjQFzX3Wak4maUWhSXstPmnbBOOKGVGfc",
)
GOOGLE_PLACES_API_KEY: str = os.getenv(
    "GOOGLE_PLACES_API_KEY",
    "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg",
)

API_TOKEN = os.getenv("API_TOKEN")
REVIEWS_SCAN_LIMIT = int(os.getenv("REVIEWS_SCAN_LIMIT", "8000"))
_G_TIMEOUT: Tuple[int, int] = (5, 15)  # (connect, read) seconds

# ─────────────────────────────────────────────────────────────
# Requests Session with Retries
# ─────────────────────────────────────────────────────────────
_google_sess: Optional[requests.Session] = None


def _google_session() -> requests.Session:
    """
    Shared requests.Session with retries for transient Google API errors.
    Retries on 429/5xx with exponential backoff.
    """
    global _google_sess
    if _google_sess is not None:
        return _google_sess

    sess = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=50)
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    _google_sess = sess
    return _google_sess

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _parse_date_param(s: Optional[str]) -> Optional[datetime]:
    """Parse 'YYYY-MM-DD' or ISO datetime; return UTC-aware or None."""
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
    """Ensure review_date is timezone-aware UTC."""
    if not dt:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _validate_token(x_api_key: Optional[str], authorization: Optional[str]) -> None:
    """Optional API token validator. No-op if API_TOKEN unset."""
    if not API_TOKEN:
        return
    token = (x_api_key or "").strip()
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token != API_TOKEN:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API token")


def _extract_city_from_components(components: List[Dict[str, Any]]) -> Optional[str]:
    """Best-effort city extractor from Google address components."""
    for comp in components or []:
        types = comp.get("types", [])
        if "locality" in types:
            return comp.get("long_name")
        if "postal_town" in types:
            return comp.get("long_name")
        if "administrative_area_level_2" in types:
            return comp.get("long_name")
    return None


def _google_places_get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Shared GET wrapper with consistent error handling + retries."""
    try:
        sess = _google_session()
        resp = sess.get(url, params=params, timeout=_G_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        status_text = payload.get("status")
        # Places/Maps APIs: treat OK and ZERO_RESULTS as non-exception
        if status_text not in ("OK", "ZERO_RESULTS"):
            # Handle common statuses gracefully
            logger.warning(f"Google Places API status: {status_text} | url={url}")
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                f"Google status: {status_text or 'UNKNOWN'}",
            )
        return payload
    except requests.RequestException as e:
        logger.error(f"Google Places request failed: {e}")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "External API error")


def _require_places_key():
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Google Places API not configured"
        )

# ─────────────────────────────────────────────────────────────
# Google Places: Autocomplete
# ─────────────────────────────────────────────────────────────
@router.get("/google/autocomplete")
def google_places_autocomplete(
    q: str = Query(..., min_length=2, description="Partial query (e.g., 'Pizza Hu')"),
    language: Optional[str] = Query(None, description="Language code (e.g., en, ur, ar)"),
    sessiontoken: Optional[str] = Query(None, description="Client-side session token for billing grouping"),
    types: Optional[str] = Query(None, description="Restrict results (e.g., 'establishment')"),
):
    """
    Places Autocomplete → returns prediction list for UI typeahead.
    """
    _require_places_key()
    params: Dict[str, Any] = {
        "input": q,
        "key": GOOGLE_PLACES_API_KEY,
    }
    if language:
        params["language"] = language
    if sessiontoken:
        params["sessiontoken"] = sessiontoken
    if types:
        params["types"] = types

    payload = _google_places_get(
        "https://maps.googleapis.com/maps/api/place/autocomplete/json", params
    )
    preds = payload.get("predictions") or []
    return {
        "ok": True,
        "items": [
            {
                "place_id": p.get("place_id"),
                "description": p.get("description"),
                "structured_formatting": p.get("structured_formatting"),
                "types": p.get("types"),
            }
            for p in preds
        ],
    }

# ─────────────────────────────────────────────────────────────
# Google Places: Find place from text (kept for compatibility)
# ─────────────────────────────────────────────────────────────
@router.get("/google/places")
def google_places_search(
    q: str = Query(..., min_length=2, description="Free text query (e.g., 'Pizza Hut Lahore')"),
    limit: int = Query(5, ge=1, le=10, description="Max candidates to return"),
    language: Optional[str] = Query(None, description="Language code (e.g., en, ur, ar)"),
):
    _require_places_key()
    params = {
        "input": q,
        "inputtype": "textquery",
        "fields": "place_id,name,formatted_address",
        "key": GOOGLE_PLACES_API_KEY,
    }
    if language:
        params["language"] = language

    payload = _google_places_get(
        "https://maps.googleapis.com/maps/api/place/findplacefromtext/json", params
    )
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

# ─────────────────────────────────────────────────────────────
# Google Places: Text Search (paged via next_page_token)
# ─────────────────────────────────────────────────────────────
@router.get("/google/search")
def google_places_text_search(
    q: Optional[str] = Query(None, description="Text search query (e.g., 'pizza in Lahore')"),
    location: Optional[str] = Query(None, description="lat,lng (e.g., '31.5204,74.3587')"),
    radius: Optional[int] = Query(None, ge=1, le=50000, description="Search radius in meters"),
    type: Optional[str] = Query(None, description="Place type (e.g., restaurant, hospital)"),
    language: Optional[str] = Query(None, description="Language code"),
    page_token: Optional[str] = Query(None, alias="next_page_token", description="Google next_page_token"),
):
    """
    Google Places Text Search with optional paging.
    Either `q` OR (`location` + `radius`) should be provided.
    Returns results + optional `next_page_token`.
    """
    _require_places_key()

    if not q and not (location and radius):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide `q` or (`location` and `radius`).")

    params: Dict[str, Any] = {
        "key": GOOGLE_PLACES_API_KEY,
    }
    if q:
        params["query"] = q
    if location:
        params["location"] = location
    if radius:
        params["radius"] = radius
    if type:
        params["type"] = type
    if language:
        params["language"] = language
    if page_token:
        # Per Google docs, next_page_token may need a short delay before use
        params["pagetoken"] = page_token
        time.sleep(2.0)

    payload = _google_places_get(
        "https://maps.googleapis.com/maps/api/place/textsearch/json", params
    )

    results = payload.get("results") or []
    next_token = payload.get("next_page_token")
    items = []
    for r in results:
        loc = (r.get("geometry") or {}).get("location") or {}
        items.append({
            "place_id": r.get("place_id"),
            "name": r.get("name"),
            "formatted_address": r.get("formatted_address"),
            "rating": r.get("rating"),
            "user_ratings_total": r.get("user_ratings_total"),
            "lat": loc.get("lat"),
            "lng": loc.get("lng"),
            "types": r.get("types"),
            "business_status": r.get("business_status"),
        })

    return {
        "ok": True,
        "items": items,
        "next_page_token": next_token,
    }

# ─────────────────────────────────────────────────────────────
# Google Places: Place Details (with optional reviews)
# ─────────────────────────────────────────────────────────────
@router.get("/google/details")
def google_place_details(
    place_id: str = Query(..., min_length=10, description="Google Place ID"),
    language: Optional[str] = Query(None, description="Language code (e.g., en, ur, ar)"),
    include_reviews: bool = Query(False, description="Include up to 5 sample Google reviews"),
):
    _require_places_key()

    fields_parts = [
        "name", "formatted_address", "formatted_phone_number", "international_phone_number",
        "website", "address_components", "geometry", "rating", "user_ratings_total", "url"
    ]
    if include_reviews:
        fields_parts.append("reviews")  # limited to up to 5 samples
    fields = ",".join(fields_parts)

    params = {
        "place_id": place_id,
        "fields": fields,
        "key": GOOGLE_PLACES_API_KEY,
    }
    if language:
        params["language"] = language

    payload = _google_places_get(
        "https://maps.googleapis.com/maps/api/place/details/json", params
    )
    result = payload.get("result") or {}
    loc = (result.get("geometry") or {}).get("location") or {}

    resp: Dict[str, Any] = {
        "place_id": place_id,
        "name": result.get("name"),
        "address": result.get("formatted_address"),
        "phone": result.get("formatted_phone_number") or result.get("international_phone_number"),
        "website": result.get("website"),
        "city": _extract_city_from_components(result.get("address_components") or []),
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
        "rating": result.get("rating"),
        "user_ratings_total": result.get("user_ratings_total"),
        "url": result.get("url"),
    }

    if include_reviews:
        g_reviews = result.get("reviews") or []
        items: List[Dict[str, Any]] = []
        for r in g_reviews:
            ts = r.get("time")
            dt_iso = None
            if isinstance(ts, (int, float)) and ts > 0:
                dt_iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            items.append({
                "author_name": r.get("author_name"),
                "author_url": r.get("author_url"),
                "profile_photo_url": r.get("profile_photo_url"),
                "rating": r.get("rating"),
                "text": r.get("text"),
                "relative_time_description": r.get("relative_time_description"),
                "time": ts,
                "review_date": dt_iso,
                "language": r.get("language"),
            })
        resp["reviews"] = items

    return resp

# ─────────────────────────────────────────────────────────────
# Dashboard Summary
# ─────────────────────────────────────────────────────────────
@router.get("/summary/{company_id}")
def reviews_summary(
    company_id: int = Path(..., ge=1),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    include_aspects: bool = Query(True),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")

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
    company_id: int = Path(..., ge=1),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    rating: Optional[int] = Query(None, ge=1, le=5),
    q: Optional[str] = Query(None, min_length=2),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    order: Literal["asc", "desc"] = Query("desc"),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")

    query = db.query(Review).filter(Review.company_id == company_id)
    start_dt = _parse_date_param(start)
    end_dt = _parse_date_param(end)

    if start_dt:
        query = query.filter(Review.review_date >= start_dt)
    if end_dt:
        query = query.filter(Review.review_date < (end_dt + timedelta(days=1)))

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
                "reviewer_avatar": getattr(r, "reviewer_avatar", None),
                "review_date": (
                    _normalize_review_date(r.review_date) or datetime.now(timezone.utc)
                ).isoformat(),
                "sentiment_category": getattr(r, "sentiment_category", None),
                "sentiment_score": getattr(r, "sentiment_score", None),
                "keywords": getattr(r, "keywords", None),
                "language": getattr(r, "language", None),
            }
            for r in items
        ],
    }

# ─────────────────────────────────────────────────────────────
# Import sample Google reviews (up to 5 from Place Details)
# ─────────────────────────────────────────────────────────────
@router.post("/google/import/{company_id}")
def import_google_reviews(
    company_id: int = Path(..., ge=1),
    place_id: str = Query(..., min_length=10),
    language: Optional[str] = Query(None),
    max_reviews: int = Query(5, ge=1, le=5),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")

    _require_places_key()

    params = {
        "place_id": place_id,
        "fields": "name,reviews",
        "key": GOOGLE_PLACES_API_KEY
    }
    if language:
        params["language"] = language

    payload = _google_places_get(
        "https://maps.googleapis.com/maps/api/place/details/json", params
    )
    result = payload.get("result") or {}
    g_reviews: List[Dict[str, Any]] = (result.get("reviews") or [])[:max_reviews]

    added = 0
    for gr in g_reviews:
        author_url = gr.get("author_url") or ""
        ts = gr.get("time")
        ext_id = f"{author_url}|{ts}" if (author_url or ts) else None

        if ext_id:
            exists = db.query(Review).filter(
                Review.company_id == company_id,
                Review.external_id == ext_id
            ).first()
            if exists:
                continue

        dt = (
            datetime.fromtimestamp(ts, tz=timezone.utc)
            if isinstance(ts, (int, float)) and ts > 0 else None
        )

        row = Review(
            company_id=company_id,
            external_id=ext_id,
            text=gr.get("text"),
            rating=gr.get("rating"),
            review_date=dt,
            reviewer_name=gr.get("author_name"),
            reviewer_avatar=gr.get("profile_photo_url"),
            sentiment_category=None,
            sentiment_score=None,
            keywords=None,
            language=gr.get("language"),
            fetch_status="Success",
        )
        db.add(row)
        added += 1

    if added:
        db.commit()

    return {"ok": True, "imported": added}

# ─────────────────────────────────────────────────────────────
# Sync Reviews (delegates to ingestion service)
# ─────────────────────────────────────────────────────────────
@router.post("/sync/{company_id}")
def reviews_sync(
    company_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    max_reviews: int = Query(60, ge=1, le=200),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")

    _validate_token(x_api_key, authorization)

    try:
        from ..services.ingestion import fetch_and_save_reviews_places
        added = fetch_and_save_reviews_places(
            company,
            db,
            max_reviews=min(max_reviews, REVIEWS_SCAN_LIMIT),
        )
        return {"ok": True, "added": int(added or 0)}
    except (ImportError, Exception) as e:
        logger.error(f"Sync failed for company {company_id}: {e}")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Review ingestion failed")

# ─────────────────────────────────────────────────────────────
# Diagnostics
# ─────────────────────────────────────────────────────────────
@router.get("/diagnostics")
def reviews_diagnostics():
    return {
        "google_maps_key_present": bool(GOOGLE_MAPS_API_KEY),
        "google_business_key_present": bool(GOOGLE_BUSINESS_API_KEY),
        "google_places_key_present": bool(GOOGLE_PLACES_API_KEY),
        "api_token_configured": bool(API_TOKEN),
        "reviews_scan_limit": REVIEWS_SCAN_LIMIT,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }

# ─────────────────────────────────────────────────────────────
# Startup Check
# ─────────────────────────────────────────────────────────────
def check_google_api_keys_at_startup():
    missing = []
    if not GOOGLE_MAPS_API_KEY: missing.append("GOOGLE_MAPS_API_KEY")
    if not GOOGLE_BUSINESS_API_KEY: missing.append("GOOGLE_BUSINESS_API_KEY")
    if not GOOGLE_PLACES_API_KEY: missing.append("GOOGLE_PLACES_API_KEY")

    if missing:
        logger.warning(f"Missing Google API keys at startup: {', '.join(missing)}")
    else:
        logger.info("All Google API keys are configured.")

check_google_api_keys_at_startup()
