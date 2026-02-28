# FILE: app/services/ingestion.py
"""
Lightweight ingestion service for pulling reviews into the database.
"""

from __future__ import annotations

import os
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session

try:
    from ..models import Company, Review
except Exception as _imp_err:  # pragma: no cover
    Company = object  # type: ignore
    Review = object   # type: ignore
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
    os.getenv("GOOGLE_MAPS_API_KEY", "")
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
    """Rating→sentiment logic matching ai_insights.py."""
    if r is None or r == 3:
        return "Neutral"
    return "Positive" if r >= 4 else "Negative"


def _google_places_get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Shared GET wrapper with consistent error handling."""
    try:
        resp = requests.get(url, params=params, timeout=_G_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        status = payload.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            logger.warning(f"Google Places API status={status} | error_message={payload.get('error_message')}")
            raise RuntimeError(f"Google Places status: {status}")
        return payload
    except requests.RequestException as e:
        logger.error(f"Google Places request failed: {e}")
        raise RuntimeError("External API error") from e


def _fetch_place_details(place_id: str, language: Optional[str] = None, include_reviews: bool = True) -> Dict[str, Any]:
    """Fetch Place Details from Google."""
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


def _upsert_review_row(
    db: Session,
    company_id: int,
    place_id: str,
    gr: Dict[str, Any],
) -> bool:
    """Idempotent insert/update of a review record."""
    ext_id = f"gplace:{place_id}:{gr.get('author_name','unknown')}:{gr.get('time')}"
    existing = (
        db.query(Review)
        .filter(Review.company_id == company_id, Review.external_id == ext_id)
        .first()
    )

    rating = gr.get("rating")
    text = gr.get("text") or None
    reviewer_name = gr.get("author_name") or None
    reviewer_avatar = gr.get("profile_photo_url") or None
    review_date = _epoch_to_utc(gr.get("time"))
    lang = gr.get("language") or None

    sent_label = _sentiment_from_rating(float(rating) if rating is not None else None)
    sent_score = 0.7 if sent_label == "Positive" else (-0.7 if sent_label == "Negative" else 0.0)

    if existing:
        dirty = False
        if existing.text != text: existing.text = text; dirty = True
        if existing.rating != rating: existing.rating = rating; dirty = True
        if existing.reviewer_name != reviewer_name: existing.reviewer_name = reviewer_name; dirty = True
        if existing.reviewer_avatar != reviewer_avatar: existing.reviewer_avatar = reviewer_avatar; dirty = True
        if existing.review_date != review_date: existing.review_date = review_date; dirty = True
        if existing.language != lang: existing.language = lang; dirty = True
        if existing.sentiment_category != sent_label: existing.sentiment_category = sent_label; dirty = True
        if (existing.sentiment_score or 0.0) != sent_score: existing.sentiment_score = sent_score; dirty = True
        
        if dirty:
            existing.fetch_status = "Success"
        return False

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
    """Pull and save recent reviews from Google Places API."""
    if _IMPORT_ERROR:
        raise RuntimeError(f"Models import error: {_IMPORT_ERROR}")

    if not isinstance(company, Company):
        raise ValueError("Invalid company object")
    if not company.place_id:
        raise ValueError("Company has no place_id")

    # Places Details API is strictly limited to 5 reviews per request.
    effective_limit = 5 
    
    logger.info(f"Syncing company_id={company.id} | place_id={company.place_id}")

    result = _fetch_place_details(company.place_id, language=language, include_reviews=True)
    g_reviews = (result.get("reviews") or [])[:effective_limit]

    created = 0
    updated = 0
    for gr in g_reviews:
        if _upsert_review_row(db, company.id, company.place_id, gr):
            created += 1
        else:
            updated += 1

    if (created + updated) > 0:
        db.commit()

    logger.info(f"Sync complete: {created} new, {updated} updated.")
    return created
