# filename: review_saas/app/services/google_reviews.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.models import Review

logger = logging.getLogger("google_reviews")


# ---------------------------------------------------------
# DATETIME PARSER
# ---------------------------------------------------------
def _coerce_datetime(value: Any) -> Optional[datetime]:
    """Safely parse Outscraper timestamps into naive UTC datetimes."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.replace(tzinfo=None)

    # numeric timestamps
    try:
        if isinstance(value, (int, float)):
            # detect milliseconds timestamp
            if value > 10_000_000_000:
                return datetime.utcfromtimestamp(value / 1000.0)
            return datetime.utcfromtimestamp(value)
    except Exception:
        pass

    # string timestamps
    if isinstance(value, str):
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try---------
# SENTIMENT CALC FROM RATING
# ---------------------------------------------------------
def _sentiment_from_rating(r: Optional[float]) -> float:
    """Convert rating (1–5) → sentiment_score (-1 to 1)."""
    if r is None:
        return 0.0
    try:
        r = max(1.0, min(5.0, float(r)))
        return round((r - 3.0) / 2.0, 2)
    except Exception:
        return 0.0


# ---------------------------------------------------------
# EXTRACT NESTED OUTSCRAPER PAYLOAD
# ---------------------------------------------------------
def _extract_reviews_from_payload(block: Any) -> List[Dict[str, Any]]:
    """Outscraper often returns nested lists. Extract clean review dicts."""
    reviews: List[Dict[str, Any]] = []

    def walk(obj: Any):
        if isinstance(obj, dict):
            # typical review list location
            if isinstance(obj.get("reviews_data"), list):
                for r in obj["reviews_data"]:
                    if isinstance(r, dict):
                        reviews.append(r)
            for v in obj.values():
                walk(v)

        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(block)
    return reviews


# ---------------------------------------------------------
# SAVE NORMALIZED REVIEWS TO DB
# ---------------------------------------------------------
async def ingest_outscraper_reviews(
    *,
    session: AsyncSession,
    company_id: int,
    raw_payloads: List[Dict[str, Any]],
) -> int:
    """
    Normalize + Insert Outscraper reviews into Postgres.
    Uses (company_id, google_review_id) unique constraint to prevent duplicates.
    """
    logger.info(f"[INGEST] Processing {len(raw_payloads)} Outscraper payload blocks")

    # Flatten nested structures
    flattened: List[Dict[str, Any]] = []
    for block in raw_payloads:
        flattened.extend(_extract_reviews_from_payload(block))

    logger.info(f"[INGEST] Extracted {len(flattened)} raw reviews")

    # Prepare normalized records
    incoming_ids: List[str] = []
    normalized: List[Dict[str, Any]] = []

    for r in flattened:
        ext_id = (
            r.get("review_id")
            or r.get("google_review_id")
            or r.get("reviewId")
            or r.get("id")
        )

        # fallback synthetic ID
        if not ext_id:
            ext_id = (
                f"{r.get('author_name','Unknown')}|"
                f"{r.get('review_timestamp','')}|"
                f"{(r.get('text') or '')[:20]}"
            )

        author = r.get("author_name") or r.get("author_title") or "Anonymous"
        rating = r.get("rating") or r.get("review_rating")
        rating_float = float(rating or 0)

        ts = r.get("review_timestamp") or r.get("time") or r.get("review_datetime_utc")
        dt = _coerce_datetime(ts) or datetime.utcnow()

        text = r.get("review_text") or r.get("text") or ""
        profile = r.get("author_image") or r.get("profile_photo_url") or ""

        item = dict(
            google_review_id=str(ext_id)[:512],
            author_name=str(author)[:255],
            rating=int(rating_float) if rating_float else None,
            text=str(text),
            google_review_time=dt,
            profile_photo_url=str(profile),
            sentiment_score=_sentiment_from_rating(rating_float),
        )

        normalized.append(item)
        incoming_ids.append(item["google_review_id"])

    logger.info(f"[INGEST] Normalized {len(normalized)} reviews")

    # Query existing review IDs to avoid duplicates
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

    logger.info(f"[INGEST] {len(existing_ids)} duplicates detected")

    # Insert new reviews
    new_count = 0
    for item in normalized:
        if item["google_review_id"] in existing_ids:
            continue

        session.add(Review(company_id=company_id, **item))
        new_count += 1

    # Commit
    if new_count > 0:
        try:
            await session.commit()
            logger.info(f"[INGEST] Saved {new_count} new reviews for company {company_id}")
        except IntegrityError:
            await session.rollback()
            logger.warning("[INGEST] IntegrityError during commit — possible race duplicate")
            new_count = 0

    return new_count
