# filename: review_saas/app/services/google_reviews.py
from __future__ import annotations
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.models import Review

logger = logging.getLogger("app.google_reviews")


def _coerce_datetime(value: Any) -> Optional[datetime]:
    """Convert many timestamp forms to naive UTC (for simpler comparisons)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    # numeric timestamps (secs or ms)
    try:
        if isinstance(value, (int, float)):
            if float(value) > 10_000_000_000:
                return datetime.utcfromtimestamp(float(value) / 1000.0)
            return datetime.utcfromtimestamp(float(value))
    except Exception:
        pass
    # strings
    if isinstance(value, str):
        formats = (
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        )
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt)
            except Exception:
                continue
    return None


def _coerce_rating(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _sentiment_from_rating(r: Optional[float]) -> float:
    """Map 1..5 stars to -1..1."""
    if r is None:
        return 0.0
    try:
        r = max(1.0, min(5.0, float(r)))
        return round((r - 3.0) / 2.0, 2)
    except Exception:
        return 0.0


def _extract_reviews_from_outscraper_payload(raw_block: Any) -> List[Dict[str, Any]]:
    """
    Outscraper responses vary; this tries to reach the array of review dicts.
    Common shapes:
      {"data":[ [{"reviews_data":[ {...}, ... ]}] ]}
      {"data":[ {"reviews_data":[...]}, ... ]}
      nested lists/dicts with 'reviews_data' somewhere inside.
    """
    reviews: List[Dict[str, Any]] = []

    def flatten_reviews(obj: Any) -> None:
        if isinstance(obj, dict):
            if "reviews_data" in obj and isinstance(obj["reviews_data"], list):
                for r in obj["reviews_data"]:
                    if isinstance(r, dict):
                        reviews.append(r)
            else:
                for v in obj.values():
                    flatten_reviews(v)
        elif isinstance(obj, list):
            for item in obj:
                flatten_reviews(item)

    flatten_reviews(raw_block)
    return reviews


async def ingest_outscraper_reviews(
    *,
    session: AsyncSession,
    company_id: int,
    raw_payloads: List[Dict[str, Any]],
) -> int:
    """
    Normalize and save reviews from Outscraper payloads into DB.
    De-duplicates on (company_id, google_review_id) unique constraint.
    Returns number of new rows saved.
    """
    # Flatten payloads into list of raw review dicts
    flattened: List[Dict[str, Any]] = []
    for block in raw_payloads:
        flattened.extend(_extract_reviews_from_outscraper_payload(block))

    new_count = 0

    # Preload existing IDs
    incoming_ids: List[str] = []
    normalized_items: List[Dict[str, Any]] = []
    for r in flattened:
        # Choose external id
        ext_id = (
            r.get("review_id")
            or r.get("google_review_id")
            or r.get("reviewId")
            or r.get("id")
        )
        # Fallback synthetic id if missing
        if not ext_id:
            author = (r.get("author_title") or r.get("author_name") or "Anonymous")
            text = (r.get("review_text") or r.get("text") or "")
            ts = r.get("review_timestamp") or r.get("time") or r.get("review_datetime_utc") or ""
            ext_id = f"{author}|{str(ts)}|{text[:32]}"

        author_name = r.get("author_title") or r.get("author_name") or "Anonymous"
        rating = _coerce_rating(r.get("review_rating") or r.get("rating"))
        when = r.get("review_timestamp") or r.get("time") or r.get("review_datetime_utc")
        dt = _coerce_datetime(when) or datetime.utcnow()
        profile = r.get("author_image") or r.get("profile_photo_url") or ""
        text = r.get("review_text") or r.get("text") or ""

        normalized_items.append(
            dict(
                google_review_id=str(ext_id)[:512],
                author_name=str(author_name)[:255],
                rating=int(rating) if rating else None,
                text=str(text),
                google_review_time=dt,
                profile_photo_url=str(profile),
                sentiment_score=_sentiment_from_rating(rating),
            )
        )
        incoming_ids.append(str(ext_id)[:512])

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

    for item in normalized_items:
        if item["google_review_id"] in existing_ids:
            continue
        session.add(Review(company_id=company_id, **item))
        new_count += 1

    if new_count > 0:
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            new_count = 0
            logger.warning("IntegrityError: likely duplicates raced during commit.")

    return new_count
