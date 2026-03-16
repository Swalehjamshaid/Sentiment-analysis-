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


# ---------------------------------------------------------
# Helper functions
# ---------------------------------------------------------

def _coerce_datetime(value: Any) -> Optional[datetime]:
    """Convert Outscraper timestamps into a Python datetime."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.replace(tzinfo=None)

    try:
        if isinstance(value, (int, float)):
            # Handle epoch in ms or seconds
            if float(value) > 10_000_000_000:
                return datetime.utcfromtimestamp(float(value) / 1000)
            return datetime.utcfromtimestamp(float(value))
    except Exception:
        pass

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
            try:
                return datetime.strptime(value, fmt)
            except Exception:
                continue

    return None


def _coerce_rating(x: Any) -> float:
    """Always return a float rating (0.0 fallback)."""
    try:
        return float(x)
    except Exception:
        return 0.0


def _sentiment_from_rating(r: Optional[float]) -> float:
    """Convert 1..5 stars into sentiment score -1..1."""
    if r is None:
        return 0.0
    try:
        r = max(1.0, min(5.0, float(r)))
        return round((r - 3.0) / 2.0, 2)
    except Exception:
        return 0.0


# ---------------------------------------------------------
# Extract reviews from Outscraper payload
# ---------------------------------------------------------

def _extract_reviews_from_outscraper_payload(payload: Any) -> List[Dict[str, Any]]:
    """
    Outscraper returns deeply nested structures; this digs out "reviews_data".
    """
    results: List[Dict[str, Any]] = []

    def walk(node: Any):
        if isinstance(node, dict):
            if "reviews_data" in node and isinstance(node["reviews_data"], list):
                for r in node["reviews_data"]:
                    if isinstance(r, dict):
                        results.append(r)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)
    return results


# ---------------------------------------------------------
# MAIN INGESTION FUNCTION
# ---------------------------------------------------------

async def ingest_outscraper_reviews(
    *,
    session: AsyncSession,
    company_id: int,
    raw_payloads: List[Dict[str, Any]],
) -> int:
    """
    Normalizes review payloads, deduplicates, and inserts into PostgreSQL.
    Returns number of NEW saved reviews.
    """
    flattened_reviews: List[Dict[str, Any]] = []

    # Flatten all Outscraper responses
    for block in raw_payloads:
        flattened_reviews.extend(_extract_reviews_from_outscraper_payload(block))

    normalized: List[Dict[str, Any]] = []
    incoming_ids: List[str] = []

    # Normalize each review
    for r in flattened_reviews:

        # Choose Outscraper review identifier
        ext_id = (
            r.get("review_id")
            or r.get("google_review_id")
            or r.get("reviewId")
            or r.get("id")
        )

        # If missing, generate fallback synthetic ID for dedupe
        if not ext_id:
            author = (r.get("author_name") or r.get("author_title") or "Anonymous")
            text = (r.get("review_text") or r.get("text") or "")
            ts = r.get("review_timestamp") or r.get("time") or r.get("review_datetime_utc") or ""
            ext_id = f"{author}|{ts}|{text[:40]}"

        rating = _coerce_rating(r.get("review_rating") or r.get("rating"))
        dt = _coerce_datetime(
            r.get("review_timestamp")
            or r.get("time")
            or r.get("review_datetime_utc")
        ) or datetime.utcnow()

        normalized.append({
            "google_review_id": str(ext_id)[:512],
            "author_name": (r.get("author_name") or r.get("author_title") or "Anonymous")[:255],
            "rating": int(rating) if rating else None,
            "text": (r.get("review_text") or r.get("text") or "").strip(),
            "google_review_time": dt,
            "profile_photo_url": str(r.get("author_image") or r.get("profile_photo_url") or ""),
            "sentiment_score": _sentiment_from_rating(rating),
        })

        incoming_ids.append(str(ext_id)[:512])

    # ---------------------------------------------------------
    # Deduplicate against existing review IDs
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # Insert only NEW reviews
    # ---------------------------------------------------------

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
        except IntegrityError:
            await session.rollback()
            new_count = 0
            logger.warning("IntegrityError: duplicate detected during commit.")

    return new_count
