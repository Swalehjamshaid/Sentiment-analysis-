# filename: app/services/review.py
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, List, Optional, Tuple

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.models import Review, Company

logger = logging.getLogger("app.services.review")

OUTSCRAPER_API_KEY = os.getenv("OUTSCRAPER_API_KEY", "").strip()
OUTSCRAPER_BASE_URL = os.getenv("OUTSCRAPER_BASE_URL", "https://api.app.outscraper.com").rstrip("/")
OUTSCRAPER_REVIEWS_URL = f"{OUTSCRAPER_BASE_URL}/maps/reviews-v3"

HTTP_TIMEOUT = httpx.Timeout(20.0, read=60.0)

# -----------------------------
# Helpers
# -----------------------------
def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        if isinstance(value, (int, float)):
            if float(value) > 10_000_000_000:
                return datetime.utcfromtimestamp(float(value) / 1000.0)
            return datetime.utcfromtimestamp(float(value))
    except Exception:
        pass
    if isinstance(value, str):
        formats = ("%Y-%m-%dT%H:%M:%S.%fZ","%Y-%m-%dT%H:%M:%S.%f","%Y-%m-%dT%H:%M:%SZ","%Y-%m-%dT%H:%M:%S","%Y-%m-%d %H:%M:%S","%Y-%m-%d",)
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt)
            except Exception:
                continue
    return None

def _coerce_rating(x: Any) -> Optional[int]:
    try:
        f = float(x)
        if f != f:
            return None
        return int(round(f))
    except Exception:
        return None

def _extract_review_blocks(raw: Any) -> List[dict[str, Any]]:
    collected: List[dict[str, Any]] = []
    def walk(obj: Any):
        if isinstance(obj, dict):
            if "reviews_data" in obj and isinstance(obj["reviews_data"], list):
                for it in obj["reviews_data"]:
                    if isinstance(it, dict):
                        collected.append(it)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
    walk(raw)
    return collected

def _dedupe_key(author: str, created_at: Optional[datetime], text: str) -> str:
    safe_author = (author or "Anonymous").strip()
    day = created_at.date().isoformat() if created_at else ""
    normalized_text = " ".join((text or "").split())
    return f"{safe_author}|{day}|{normalized_text[:64]}"

# -----------------------------
# Public API
# -----------------------------
async def ingest_outscraper_reviews(company: Company, session: AsyncSession, max_reviews: int = 200) -> int:
    if not OUTSCRAPER_API_KEY:
        logger.warning("OUTSCRAPER_API_KEY missing; skipping ingestion.")
        return 0

    query = company.google_place_id or company.name
    if company.address and query == company.name:
        query = f"{company.name}, {company.address}"

    params = {"query": query, "reviewsLimit": max_reviews, "async": "false"}
    headers = {"X-API-KEY": OUTSCRAPER_API_KEY}

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            resp = await client.get(OUTSCRAPER_REVIEWS_URL, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.exception("Outscraper fetch failed for company %s: %s", company.id, e)
            return 0

    raw_reviews = []
    for block in data if isinstance(data, list) else [data]:
        raw_reviews.extend(_extract_review_blocks(block))

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

    # Load existing to avoid duplicates
    existing_sigs = set()
    try:
        one_year_ago = datetime.utcnow().replace(year=datetime.utcnow().year - 1)
        res = await session.execute(select(Review.author, Review.created_at, Review.text)
                                    .where(and_(Review.company_id == company.id,
                                                Review.created_at >= one_year_ago)))
        rows = res.all()
        for a, ts, t in rows:
            existing_sigs.add(_dedupe_key(a or "Anonymous", ts, t or ""))
    except Exception as e:
        logger.warning("Failed precompute for company %s: %s", company.id, e)

    new_count = 0
    for (author, rating, text, created_at), sig in zip(normalized, sigs):
        if sig in existing_sigs:
            continue
        session.add(Review(company_id=company.id, author=author, rating=rating, text=text, created_at=created_at))
        new_count += 1

    if new_count > 0:
        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception("Failed commit %s reviews for company %s: %s", new_count, company.id, e)
            return 0

    return new_count
