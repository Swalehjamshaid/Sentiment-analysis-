# filename: app/services/review.py
"""
Modern, clean, Postgres‑ready Outscraper integration.
Compatible with: app/core/models.py, async SQLAlchemy, google_reviews ingestion.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Company, Review  # FIXED IMPORT

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------------
OUTSCRAPER_API_KEY = os.getenv("OUTSCRAPER_API_KEY", "").strip()
OUTSCRAPER_BASE_URL = os.getenv("OUTSCRAPER_BASE_URL", "https://api.app.outscraper.com").rstrip("/")
OUTSCRAPER_SEARCH_URL = f"{OUTSCRAPER_BASE_URL}/maps/search-v2"
OUTSCRAPER_REVIEWS_URL = f"{OUTSCRAPER_BASE_URL}/maps/reviews-v3"

HTTP_TIMEOUT = httpx.Timeout(20.0, read=60.0)
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3

SEARCH_FIELDS = (
    "query,name,full_address,site,phone,rating,reviews,"
    "latitude,longitude,place_id,google_id,cid"
)

# -------------------------------------------------------------------------
# UTILS
# -------------------------------------------------------------------------
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalized_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _coerce_datetime(value: Any) -> datetime:
    """Parse Outscraper timestamps safely."""
    from app.services.google_reviews import _coerce_datetime as conv
    return conv(value) or _now_utc()


def _coerce_rating(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _sentiment_from_rating(r: Optional[float]) -> float:
    if r is None:
        return 0.0
    try:
        r = max(1, min(5, float(r)))
        return round((r - 3) / 2, 2)
    except Exception:
        return 0.0


# -------------------------------------------------------------------------
# HTTP CALLS (RESILIENT)
# -------------------------------------------------------------------------
async def _request(client: httpx.AsyncClient, method: str, url: str, *, params=None) -> Any:
    """Retries with exponential backoff."""
    headers = {"X-API-KEY": OUTSCRAPER_API_KEY}
    attempt = 0
    backoff = 1.0

    while True:
        attempt += 1
        try:
            resp = await client.request(method, url, headers=headers, params=params)
            if resp.status_code in RETRY_STATUS and attempt < MAX_RETRIES:
                logger.warning(
                    "Outscraper %s %s → %s. Retrying in %.1fs (%s/%s)",
                    method, url, resp.status_code, backoff, attempt, MAX_RETRIES
                )
                await asyncio.sleep(backoff)
                backoff *= 2
                continue

            resp.raise_for_status()
            return resp.json()

        except Exception as e:
            if attempt >= MAX_RETRIES:
                logger.error("Request failed after retries: %s %s %s", method, url, e)
                raise
            await asyncio.sleep(backoff)
            backoff *= 2


# -------------------------------------------------------------------------
# COMPANY DETAIL FETCH
# -------------------------------------------------------------------------
async def fetch_company_from_outscraper(query: str) -> Dict[str, Any]:
    if not OUTSCRAPER_API_KEY:
        raise RuntimeError("OUTSCRAPER_API_KEY not configured")

    params = {
        "query": query,
        "limit": 1,
        "async": "false",
        "fields": SEARCH_FIELDS,
    }

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        data = await _request(client, "GET", OUTSCRAPER_SEARCH_URL, params=params)

    if not isinstance(data, dict) or "data" not in data:
        return {}

    list_block = data["data"]
    if not list_block:
        return {}

    # common structures: nested list or flat list
    items = list_block[0] if isinstance(list_block[0], list) else list_block
    if not items:
        return {}

    item = items[0]

    return {
        "name": item.get("name"),
        "full_address": item.get("full_address"),
        "phone": item.get("phone"),
        "site": item.get("site") or item.get("website"),
        "rating": item.get("rating"),
        "reviews_count": item.get("reviews"),
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "place_id": item.get("place_id") or item.get("google_id") or item.get("cid"),
    }


# -------------------------------------------------------------------------
# REVIEW FETCH (RAW)
# -------------------------------------------------------------------------
async def fetch_reviews_from_outscraper(query: str, limit: int = 200) -> List[Dict[str, Any]]:
    if not OUTSCRAPER_API_KEY:
        raise RuntimeError("OUTSCRAPER_API_KEY not configured")

    params = {
        "query": query,
        "reviewsLimit": limit,
        "async": "false",
    }

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        data = await _request(client, "GET", OUTSCRAPER_REVIEWS_URL, params=params)

    from app.services.google_reviews import _extract_reviews_from_outscraper_payload
    return _extract_reviews_from_outscraper_payload(data)


# -------------------------------------------------------------------------
# MAIN SYNC METHOD (COMPANY DETAILS + REVIEWS)
# -------------------------------------------------------------------------
async def update_company_from_outscraper(company: Company, session: AsyncSession):
    """
    Sync a company's details AND reviews.
    Uses google_place_id if available, otherwise name+address.
    """
    try:
        # ---------------------------
        # 1) Build query
        # ---------------------------
        query = company.google_place_id or company.name
        if company.address and query == company.name:
            query = f"{company.name}, {company.address}"

        # ---------------------------
        # 2) Fetch company metadata
        # ---------------------------
        details = await fetch_company_from_outscraper(query)
        if details:
            company.full_address = details.get("full_address") or company.full_address
            company.phone = details.get("phone") or company.phone
            company.website = details.get("site") or company.website
            company.rating = details.get("rating") or company.rating
            company.reviews_count = details.get("reviews_count") or company.reviews_count

            if details.get("place_id") and not company.google_place_id:
                company.google_place_id = details["place_id"]

            company.last_synced_at = _now_utc()
            await session.flush()

        # ---------------------------
        # 3) Fetch & save reviews
        # ---------------------------
        raw_reviews = await fetch_reviews_from_outscraper(query, limit=200)
        saved = await save_outscraper_reviews(company, raw_reviews, session)

        logger.info("Company %s synced: %s new reviews", company.id, saved)

    except Exception as e:
        logger.exception("Sync failed for company %s: %s", company.id, e)
        raise


# -------------------------------------------------------------------------
# SAVE REVIEWS TO DB (DE-DUP)
# -------------------------------------------------------------------------
async def save_outscraper_reviews(
    company: Company,
    raw_reviews: List[Dict[str, Any]],
    session: AsyncSession,
) -> int:

    normalized = []
    for r in raw_reviews:
        ext_id = (
            r.get("review_id")
            or r.get("google_review_id")
            or r.get("id")
        )

        if not ext_id:
            # fallback synthetic ID
            ext_id = hashlib.md5(
                f"{company.id}|{r.get('author_name')}|{r.get('text')}".encode()
            ).hexdigest()

        rating = _coerce_rating(r.get("rating"))
        dt = _coerce_datetime(r.get("created_at"))

        normalized.append(
            dict(
                google_review_id=str(ext_id)[:512],
                author_name=r.get("author_name") or "Anonymous",
                rating=int(rating) if rating else None,
                text=_normalized_text(r.get("text") or ""),
                google_review_time=dt,
                profile_photo_url="",
                sentiment_score=_sentiment_from_rating(rating),
            )
        )

    # preload to avoid duplicates
    incoming_ids = [n["google_review_id"] for n in normalized]

    res = await session.execute(
        select(Review.google_review_id).where(
            and_(
                Review.company_id == company.id,
                Review.google_review_id.in_(incoming_ids),
            )
        )
    )
    existing = set(res.scalars().all())

    count = 0

    for r in normalized:
        if r["google_review_id"] in existing:
            continue

        session.add(Review(company_id=company.id, **r))
        count += 1

    if count:
        await session.commit()

    return count
