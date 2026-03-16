from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.models import Review

logger = logging.getLogger("app.google_reviews")


# -------------------------------------------------------
# TIME & VALUE NORMALIZATION
# -------------------------------------------------------

def _coerce_datetime(value: Any) -> Optional[datetime]:
    """Convert many timestamp formats (ISO, ms, seconds, etc.) into naive UTC datetime."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.replace(tzinfo=None)

    # Numeric timestamps
    try:
        if isinstance(value, (int, float)):
            # Milliseconds
            if float(value) > 10_000_000_000:
                return datetime.utcfromtimestamp(float(value) / 1000)
            # Seconds
            return datetime.utcfromtimestamp(float(value))
    except Exception:
        pass

    # String timestamps
    if isinstance(value, str):
        formats = (
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-% in formats:
            try:
                return datetime.strptime(value, fmt)
            except Exception:
                continue

    return None


def _coerce_rating(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _sentiment_from_rating(stars: Optional[float]) -> float:
    """
    Convert rating 1..5 to sentiment -1..1.
    """
    if stars is None:
        return 0.0
    try:
        stars = max(1.0, min(5.0, float(stars)))
        return round((stars - 3.0) / 2.0, 2)
    except Exception:
        return 0.0


# -------------------------------------------------------
# OUTSCRAPER DATA FLATTENING
# -------------------------------------------------------

def _extract_outscraper_reviews(raw: Any) -> List[Dict[str, Any]]:
    """
    Outscraper responses vary deeply. This function finds all review objects
    inside ANY nested container.
    """
    reviews: List[Dict[str, Any]] = []

    def scan(obj: Any):
        if isinstance(obj, dict):
            # Direct match
            if isinstance(obj.get("reviews_data"), list):
                for r in obj["reviews_data"]:
                    if isinstance(r, dict):
                        reviews.append(r)
            # Continue scanning nested
            for v in obj.values():
                scan(v)

        elif isinstance(obj, list):
            for item in obj:
                scan(item)

    scan(raw)
    return reviews


# -------------------------------------------------------
# INGESTION LOGIC
# -------------------------------------------------------

async def ingest_outscraper_reviews(
    *,
    session: AsyncSession,
    company_id: int,
    raw_payloads: List[Dict[str, Any]],
) -> int:
    """
    Normalizes Outscraper results and inserts new reviews into DB.
    Enforces deduplication via the unique constraint on:
        (company_id, google_review_id)
    """
    # Flatten nested payloads into review list
    extracted: List[Dict[str, Any]] = []
    for payload in raw_payloads:
        extracted.extend(_extract_outscraper_reviews(payload))

    if not extracted:
        logger.info("No Outscraper reviews found for company %s", company_id)
        return 0

    normalized: List[Dict[str, Any]] = []
    incoming_ids: List[str] = []

    for raw in extracted:
        # unique ID (Outscraper sometimes uses many different keys)
        ext_id = (
            raw.get("review_id")
            or raw.get("google_review_id")
            or raw.get("reviewId")
            or raw.get("id")
        )

        # fallback ID
        if not ext_id:
            author = raw.get("author_name") or raw.get("author_title") or "Anonymous"
            text = raw.get("review_text") or raw.get("text") or ""
            ts = raw.get("review_timestamp") or raw.get("review_datetime_utc") or ""
            ext_id = f"{author}|{ts}|{text[:30]}"

        author_name = raw.get("author_name") or raw.get("author_title") or "Anonymous"
        rating = _coerce_rating(raw.get("rating") or raw.get("review_rating"))
        dt = _coerce_datetime(
            raw.get("review_datetime_utc")
            or raw.get("datetime_utc")
            or raw.get("review_timestamp")
            or raw.get("time")
        ) or datetime.utcnow()

        normalized.append({
            "google_review_id": str(ext_id)[:512],
            "author_name": str(author_name)[:255],
            "rating": int(rating) if rating else None,
            "text": str(raw.get("review_text") or raw.get("text") or ""),
            "google_review_time": dt,
            "profile_photo_url": str(raw.get("profile_photo_url") or raw.get("author_image") or ""),
            "sentiment_score": _sentiment_from_rating(rating),
        })

        incoming_ids.append(str(ext_id)[:512])

    # Load existing IDs to prevent duplicate inserts
    existing_ids: set[str] = set()

    if incoming_ids:
        res = await session.execute(
            select(Review.google_review_id).where(
                and_(
                    Review.company_id == company_id,
                    Review.google_review_id.in_(incoming_ids),
                )
            )
        )
        existing_ids = set(res.scalars().all())

    # Insert new reviews
    new_count = 0

    for data in normalized:
        if data["google_review_id"] in existing_ids:
            continue

        session.add(
            Review(
                company_id=company_id,
                **data
            )
        )
        new_count += 1

    # Commit safely
    try:
        if new_count > 0:
            await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.warning("Possible race condition duplicate")
        new_count = 0

    return new_count
