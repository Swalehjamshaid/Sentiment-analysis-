# FILE: app/services/ingestion.py
"""
Lightweight ingestion service for pulling reviews into the database.

This module is intentionally minimal and self-contained so it can be called
directly from routes (e.g., /api/reviews/sync). It currently supports:

1) Google Places "Place Details" reviews (up to 5 sample reviews per Google)
   - Uses GOOGLE_PLACES_API_KEY or falls back to GOOGLE_MAPS_API_KEY.
   - Idempotent upsert using Review.external_id unique per company.

2) (Optional stub) Google Business Profile (GBP) – requires OAuth 2.0 in real use
   - Here only a placeholder helper is provided and NOT used by default.

Functions you’ll call from routes:
- fetch_and_save_reviews_places(company: Company, db: Session, max_reviews=60, language=None) -> int

Integration:
- Used by app/routes/reviews.py -> /api/reviews/sync/{company_id}
- Also aligned with app/routes/companies.py sync endpoint.

Notes:
- Google Places "Place Details" returns only a sample (max 5) reviews.
- For production-grade syncs, wire a proper GBP OAuth flow or a third-party
  ingestion pipeline. This module is a safe default that won’t break dashboards.
"""

from __future__ import annotations

import os
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session

try:
    # Local runtime imports; if tooling imports this module without the app installed,
    # we avoid crashing at import-time.
    from ..models import Company, Review
except Exception as _imp_err:  # pragma: no cover
    Company = object  # type: ignore
    Review = object  # type: ignore
    _IMPORT_ERROR = _imp_err
else:
    _IMPORT_ERROR = None


# ─────────────────────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────────────────────
logger = logging.getLogger("ingestion")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────
GOOGLE_PLACES_API_KEY: str = os.getenv(
    "GOOGLE_PLACES_API_KEY",
    os.getenv("GOOGLE_MAPS_API_KEY", "")  # fallback if dedicated key not set
)
_G_TIMEOUT: Tuple[int, int] = (5, 15)  # (connect, read) seconds


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _epoch_to_utc(ts: Optional[int]) -> Optional[datetime]:
    """Convert Unix epoch seconds into timezone-aware UTC datetime."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except Exception:
        return None


def _sentiment_from_rating(r: Optional[float]) -> str:
    """Rating→sentiment: 4–5 Positive, 3/None Neutral, 1–2 Negative."""
    if r is None or r == 3:
        return "Neutral"
    return "Positive" if r >= 4 else "Negative"


def _google_places_get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Shared GET wrapper with consistent error handling for Places endpoints."""
    try:
        resp = requests.get(url, params=params, timeout=_G_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        status = payload.get("status")
        # Places APIs usually return OK or ZERO_RESULTS. Others are treated as errors.
        if status not in ("OK", "ZERO_RESULTS"):
            logger.warning(f"Google Places API status={status} | error_message={payload.get('error_message')}")
            raise RuntimeError(f"Google Places status: {status}")
        return payload
    except requests.RequestException as e:
        logger.error(f"Google Places request failed: {e}")
        raise RuntimeError("External API error") from e


def _fetch_place_details(place_id: str, language: Optional[str] = None, include_reviews: bool = True) -> Dict[str, Any]:
    """Fetch Place Details. If include_reviews=True, also request 'reviews' field (max 5)."""
    if not GOOGLE_PLACES_API_KEY:
        raise RuntimeError("Google Places API key not configured")

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    fields = [
        "name", "formatted_address", "address_components", "geometry",
        "website", "international_phone_number", "rating",
        "user_ratings_total", "url",
    ]
    if include_reviews:
        fields.append("reviews")

    params: Dict[str, Any] = {
        "place_id": place_id,
        "fields": ",".join(fields),
        "key": GOOGLE_PLACES_API_KEY,
    }
    if language:
        params["language"] = language

    payload = _google_places_get(url, params)
    return payload.get("result") or {}


def _normalize_gplaces_reviews(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Normalize Google Place Details 'reviews' array into a list of dictionaries
    we can upsert into the DB.
    """
    items: List[Dict[str, Any]] = []
    for r in result.get("reviews") or []:
        ts = r.get("time")  # unix seconds
        items.append({
            "author_name": r.get("author_name"),
            "author_url": r.get("author_url"),
            "profile_photo_url": r.get("profile_photo_url"),
            "rating": r.get("rating"),
            "text": r.get("text"),
            "language": r.get("language"),
            "time": ts,
        })
    return items


def _upsert_review_row(
    db: Session,
    company_id: int,
    place_id: str,
    gr: Dict[str, Any],
) -> bool:
    """
    Insert or update a single review record.
    Returns True if created, False if updated or skipped.
    """
    # Stable external_id for idempotency (aligns with other routes' logic)
    ext_id = f"gplace:{place_id}:{gr.get('author_name','unknown')}:{gr.get('time')}"
    existing = (
        db.query(Review)
        .filter(Review.company_id == company_id, Review.external_id == ext_id)
        .first()
    )

    rating = gr.get("rating")
    rating = int(rating) if isinstance(rating, (int, float)) else None
    text = gr.get("text") or None
    reviewer_name = gr.get("author_name") or None
    reviewer_avatar = gr.get("profile_photo_url") or None
    review_date = _epoch_to_utc(gr.get("time"))
    lang = gr.get("language") or None

    sent_label = _sentiment_from_rating(float(rating) if rating is not None else None)
    sent_score = 0.0
    if sent_label == "Positive":
        sent_score = 0.7
    elif sent_label == "Negative":
        sent_score = -0.7

    if existing:
        # Update only delta fields to minimize write load
        dirty = False
        if existing.text != text:
            existing.text = text; dirty = True
        if existing.rating != rating:
            existing.rating = rating; dirty = True
        if existing.reviewer_name != reviewer_name:
            existing.reviewer_name = reviewer_name; dirty = True
        if existing.reviewer_avatar != reviewer_avatar:
            existing.reviewer_avatar = reviewer_avatar; dirty = True
        if (existing.review_date or None) != review_date:
            existing.review_date = review_date; dirty = True
        if existing.language != lang:
            existing.language = lang; dirty = True
        if existing.sentiment_category != sent_label:
            existing.sentiment_category = sent_label; dirty = True
        if (existing.sentiment_score or 0.0) != sent_score:
            existing.sentiment_score = sent_score; dirty = True
        if dirty:
            existing.fetch_status = "Success"
        return False

    # Create new row
    row = Review(
        company_id=company_id,
        external_id=ext_id,
        text=text,
        rating=rating,
        review_date=review_date,
        reviewer_name=reviewer_name,
        reviewer_avatar=reviewer_avatar,
        sentiment_category=sent_label,
        sentiment_score=sent_score,
        keywords=None,
        language=lang,
        fetch_status="Success",
    )
    db.add(row)
    return True


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────
def fetch_and_save_reviews_places(
    company: Company,
    db: Session,
    max_reviews: int = 60,
    language: Optional[str] = None,
) -> int:
    """
    Pull recent reviews from Google Places 'Place Details' for the given company,
    and upsert them into the database.

    Parameters
    ----------
    company : Company
        ORM instance with .id and .place_id populated.
    db : Session
        SQLAlchemy session (transaction handled here).
    max_reviews : int
        Desired maximum number of reviews to ingest (note: Places Details returns
        at most 5 reviews; this value is effectively capped at 5 in this method).
    language : Optional[str]
        Language code (e.g., 'en', 'ur', 'ar') for Google’s response.

    Returns
    -------
    int
        Number of newly created reviews.
    """
    if _IMPORT_ERROR:
        raise RuntimeError(f"Models import error: {_IMPORT_ERROR}")

    if not isinstance(company, Company):
        raise ValueError("Invalid company object (expected Company ORM instance)")
    if not company.place_id:
        raise ValueError("Company has no place_id configured")

    # Google returns up to 5 reviews from Place Details.
    effective_limit = min(int(max_reviews or 0) or 5, 5)
    if not GOOGLE_PLACES_API_KEY:
        raise RuntimeError("Google Places API key not configured")

    logger.info(
        f"Ingestion: fetching up to {effective_limit} reviews via Place Details "
        f"for company_id={company.id} place_id={company.place_id} lang={language or 'default'}"
    )

    result = _fetch_place_details(company.place_id, language=language, include_reviews=True)
    g_reviews = _normalize_gplaces_reviews(result)[:effective_limit]

    created = 0
    updated = 0
    for gr in g_reviews:
        was_created = _upsert_review_row(db, company.id, company.place_id, gr)
        if was_created:
            created += 1
        else:
            updated += 1

    if (created + updated) > 0:
        db.commit()

    logger.info(
        f"Ingestion completed for company_id={company.id} "
        f"(created={created}, updated={updated}, fetched={len(g_reviews)})"
    )
    return created


# ─────────────────────────────────────────────────────────────
# (Optional) GBP placeholder – not used by default
# ─────────────────────────────────────────────────────────────
def fetch_and_save_reviews_gbp(*args, **kwargs):  # pragma: no cover
    """
    Placeholder for Google Business Profile ingestion (requires OAuth 2.0).
    Implement your OAuth client and use GBP endpoints to fetch full review feed.
    This function is NOT used by default by routes.
    """
    raise NotImplementedError(
        "Google Business Profile ingestion requires OAuth 2.0. "
        "Implement your authorized client and list reviews per location."
    )
