# filename: app/services/review.py

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Review, Company

logger = logging.getLogger("app.services.review")

# -----------------------------
# Config
# -----------------------------
OUTSCRAPER_API_KEY = os.getenv("OUTSCRAPER_API_KEY", "").strip()
OUTSCRAPER_BASE_URL = os.getenv("OUTSCRAPER_BASE_URL", "https://api.app.outscraper.com").rstrip("/")
OUTSCRAPER_REVIEWS_URL = f"{OUTSCRAPER_BASE_URL}/maps/reviews-v3"

HTTP_TIMEOUT = httpx.Timeout(20.0, read=60.0)


# -----------------------------
# Helpers
# -----------------------------
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


def _coerce_rating(x: Any) -> Optional[int]:
    try:
        f = float(x)
        if f != f:  # NaN
            return None
        return int(round(f))
    except Exception:
        return None


def _extract_review_blocks(raw: Any) -> List[Dict[str, Any]]:
    """
    Outscraper payloads are nested. This digs out the array(s) of review dicts.
    Common patterns contain 'reviews_data'.
    """
    collected: List[Dict[str, Any]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if "reviews_data" in obj and isinstance(obj["reviews_data"], list):
                for it in obj["reviews_data"]:
                    if isinstance(it, dict):
                        collected.append(it)
            # keep searching deeper
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(raw)
    return collected


def _dedupe_key(author: str, created_at: Optional[datetime], text: str) -> str:
    """
    Create a simple signature to avoid inserting obvious duplicates:
      author|YYYY-MM-DD|first 64 chars of normalized text
    """
    safe_author = (author or "Anonymous").strip()
    day = created_at.date().isoformat() if created_at else ""
    normalized_text = " ".join((text or "").split())
    return f"{safe_author}|{day}|{normalized_text[:64]}"


async def _fetch_outscraper(company: Company, max_reviews: int = 200) -> List[Dict[str, Any]]:
    """
    Calls Outscraper Reviews endpoint and returns raw JSON blocks (list of dicts).
    """
    if not OUTSCRAPER_API_KEY:
        logger.warning("OUTSCRAPER_API_KEY missing; ingestion will skip.")
        return []

    query = company.google_place_id or company.name
    if company.address and query == company.name:
        query = f"{company.name}, {company.address}"

    params = {
        "query": query,
        "reviewsLimit": max_reviews,
        "async": "false",
        # Optional: "sort": "newest", "ignoreEmpty": "true", "language": "en"
    }

    headers = {"X-API-KEY": OUTSCRAPER_API_KEY}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(OUTSCRAPER_REVIEWS_URL, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

    # Normalize top-level to list of dicts for downstream walking
    if isinstance(data, list):
        return data
    return [data]
# -----------------------------
# Public API used by routes
# -----------------------------
async def ingest_outscraper_reviews(company: Company, session: AsyncSession, *, max_reviews: int = 200) -> int:
    """
    Fetch reviews from Outscraper for the given company and save them into Postgres.
    Aligns with your routes/reviews.py expectations:
      - model fields: author, rating, text, created_at
      - returns the count of newly saved rows

    NOTE: Your current BackgroundTasks usage passes the request-bound session into a
    background task. If the request finishes, that session might be closed. If you
    see 'Session is closed' errors, create a NEW session inside this function
    (import your session factory) rather than using the injected one.
    """
    try:
        raw_blocks = await _fetch_outscraper(company, max_reviews=max_reviews)
    except httpx.HTTPError as e:
        logger.exception("Outscraper HTTP error for company %s: %s", company.id, e)
        return 0
    except Exception as e:
        logger.exception("Outscraper unexpected error for company %s: %s", company.id, e)
        return 0

    if not raw_blocks:
        return 0

    # Flatten to raw review dicts
    raw_reviews = []
    for block in raw_blocks:
        raw_reviews.extend(_extract_review_blocks(block))

    if not raw_reviews:
        return 0

    # Build normalized rows and dedupe keys
    normalized: List[Tuple[str, Optional[int], str, datetime]] = []
    sigs: List[str] = []

    for r in raw_reviews:
        author = (r.get("author_title") or r.get("author_name") or "Anonymous").strip()
        rating = _coerce_rating(r.get("review_rating") or r.get("rating"))
        text = str(r.get("review_text") or r.get("text") or "").strip()

        dt_raw = r.get("review_timestamp") or r.get("time") or r.get("review_datetime_utc")
        created_at = _coerce_datetime(dt_raw) or datetime.utcnow()

        sig = _dedupe_key(author, created_at, text)

        normalized.append((author, rating, text, created_at))
        sigs.append(sig)

    # Load existing signatures from DB (best-effort)
    # We don't have a dedicated column/unique index for this signature—so we try to match
    # existing rows by same author, created_at DATE, and text prefix.
    # This is a heuristic to avoid obvious duplicates.
    existing_sigs: set[str] = set()
    try:
        # Pull recent reviews only to limit scan cost (e.g., last 12 months)
        # If you have a huge dataset, consider adding an indexed materialized signature column.
        one_year_ago = datetime.utcnow().replace(year=datetime.utcnow().year - 1)
        res = await session.execute(
            select(Review.author, Review.created_at, Review.text)
            .where(
                and_(
                    Review.company_id == company.id,
                    Review.created_at >= one_year_ago,
                )
            )
        )
        rows = res.all()
        for a, ts, t in rows:
            existing_sigs.add(_dedupe_key(a or "Anonymous", ts, t or ""))
    except Exception as e:
        logger.warning("Failed to precompute existing signatures for company %s: %s", company.id, e)

    new_count = 0
    for (author, rating, text, created_at), sig in zip(normalized, sigs):
        if sig in existing_sigs:
            continue
        session.add(
            Review(
                company_id=company.id,
                author=author,          # <-- aligns to your routes/reviews.py
                rating=rating,
                text=text,
                created_at=created_at,  # <-- aligns to your routes/reviews.py
            )
        )
        new_count += 1

    if new_count > 0:
        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception("Failed to commit %s reviews for company %s: %s", new_count, company.id, e)
            return 0

    return new_count
