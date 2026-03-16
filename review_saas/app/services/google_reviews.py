# filename: review_saas/app/services/google_reviews.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.models import Review

logger = logging.getLogger("app.google_reviews")


# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------

def _coerce_datetime(value: Any) -> Optional[datetime]:
    """Universal parser for timestamps or strings — always returns naive UTC."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.replace(tzinfo=None)

    # Timestamp (seconds or milliseconds)
    try:
        if isinstance(value, (int, float)):
            if value > 10_000_000_000:  # ms
                return datetime.utcfromtimestamp(value / 1000.0)
            return datetime.utcfromtimestamp(float(value))
    except Exception:
        pass

    # String formats
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


def _coerce_rating(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _sentiment_from_rating(r: float) -> float:
    try:
        r = max(1.0, min(5.0, float(r)))
        return round((r - 3.0) / 2.0, 2)
    except Exception:
        return 0.0


def _extract_reviews_from_payload(raw: Any) -> List[Dict[str, Any]]:
    """
    Outscraper returns deeply nested structures; this safely extracts review dicts.
    """
    reviews: List[Dict[str, Any]] = []

    def walk(obj: Any):
        if isinstance(obj, dict):
            if "reviews_data" in obj and isinstance(obj["reviews_data"], list):
                for r in obj["reviews_data"]:
                    if isinstance(r, dict):
                        reviews.append(r)
            else:
                for v in obj.values():
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(raw)
    return reviews


# --------------------------------------------------------------------------
# INGESTION PIPELINE
# --------------------------------------------------------------------------

async def ingest_outscraper_reviews(
    *,
    session: AsyncSession,
    company_id: int,
    raw_payloads: List[Dict[str, Any]],
) -> int:
    """
    Normalize, dedupe and save Outscraper reviews into DB.
    Returns number of saved reviews.
    """

    # Flatten payloads
    raw_reviews: List[Dict[str, Any]] = []
    for block in raw_payloads:
        raw_reviews.extend(_extract_reviews_from_payload(block))

    normalized: List[Dict[str, Any]] = []
    incoming_ids: List[str] = []

    for r in raw_reviews:
        # External ID priority
        ext_id = (
            r.get("review_id")
            or r.get("google_review_id")
            or r.get("reviewId")
            or r.get("id")
        )

        # Fallback synthetic ID if missing (still unique & stable)
        if not ext_id:
            author = r.get("author_title") or r.get("author_name") or "Anonymous"
            text = (r.get("review_text") or r.get("text") or "")[:32]
            ts = r.get("review_timestamp") or r.get("time") or ""
            ext_id = f"{author}|{ts}|{text}"

        author_name = r.get("author_title") or r.get("author_name") or "Anonymous"
        rating = _coerce_rating(r.get("review_rating") or r.get("rating"))
        text = r.get("review_text") or r.get("text") or ""
        when = _coerce_datetime(
            r.get("review_timestamp") or r.get("time") or r.get("review_datetime_utc")
        ) or datetime.utcnow()
        photo = r.get("author_image") or r.get("profile_photo_url") or ""

        normalized.append(
            {
                "google_review_id": str(ext_id)[:512],
                "author_name": str(author_name)[:255],
                "rating": int(rating) if rating > 0 else None,
                "text": text,
                "google_review_time": when,
                "profile_photo_url": photo,
                "sentiment_score": _sentiment_from_rating(rating),
            }
        )

        incoming_ids.append(str(ext_id)[:512])

    # ----------------------------------------------------------------------
    # Deduplicate existing reviews
    # ----------------------------------------------------------------------
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

    # ----------------------------------------------------------------------
    # INSERT new reviews
    # ----------------------------------------------------------------------
    new_count = 0
    for item in normalized:
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
            logger.warning("Duplicate race in commit — inserts rolled back.")

    return new_count
