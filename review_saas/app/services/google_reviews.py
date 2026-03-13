# filename: app/services/google_reviews.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Union

from sqlalchemy import and_, select

from app.core.db import get_session
from app.core.models import Review

logger = logging.getLogger("app.google_reviews")

# ──────────────────────────────────────────────────────────────────────────────
# Data models for normalized review ingestion/analytics
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ReviewData:
    company_id: int
    author_name: str
    rating: float
    text: str
    review_time: datetime
    profile_photo_url: str = ""
    external_review_id: Optional[str] = None   # e.g., google_review_id
    source_platform: str = "Google"
    sentiment_score: Optional[float] = None
    additional_fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompanyReviews:
    company_id: int
    reviews: List[ReviewData] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.reviews)

    @property
    def avg_rating(self) -> float:
        if not self.reviews:
            return 0.0
        return round(sum(float(r.rating or 0) for r in self.reviews) / max(1, len(self.reviews)), 3)

    @property
    def min_rating(self) -> float:
        return min((float(r.rating) for r in self.reviews), default=0.0)

    @property
    def max_rating(self) -> float:
        return max((float(r.rating) for r in self.reviews), default=0.0)

    @property
    def distribution(self) -> Dict[int, int]:
        dist = {i: 0 for i in range(1, 6)}
        for r in self.reviews:
            try:
                rr = int(round(float(r.rating)))
            except Exception:
                rr = 0
            if 1 <= rr <= 5:
                dist[rr] += 1
        return dist


# ──────────────────────────────────────────────────────────────────────────────
# Normalization helpers
# ──────────────────────────────────────────────────────────────────────────────
def _coerce_datetime(value: Any) -> Optional[datetime]:
    """Accepts UNIX ts (sec/ms), ISO strings, or datetime; returns naive datetime (UTC-assumed)."""
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
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(value, fmt)
            except Exception:
                continue
    return None


class OutscraperReviewsService:
    """Lightweight normalizer that converts raw API JSON to ReviewData.
    The client must provide an async `fetch_reviews(entity, max_reviews=None)` method that returns
    a list of dicts with keys resembling Google/Outscraper responses.
    """

    def __init__(self, source_platform: str = "Google") -> None:
        self.source_platform = source_platform

    def normalize(self, raw: Dict[str, Any], company_id: int) -> Optional[ReviewData]:
        if not raw:
            return None
        author = raw.get("author_name") or raw.get("author") or raw.get("user") or "Anonymous"
        text = raw.get("text") or raw.get("review_text") or raw.get("content") or ""
        rating = raw.get("rating") or raw.get("stars") or raw.get("score") or 0
        try:
            rating = float(rating)
        except Exception:
            rating = 0.0
        when = raw.get("time") or raw.get("review_time") or raw.get("date") or raw.get("time_timestamp")
        dt = _coerce_datetime(when) or datetime.utcnow()
        profile = raw.get("profile_photo_url") or raw.get("avatar") or ""
        external_id = raw.get("google_review_id") or raw.get("review_id") or raw.get("id")
        sent = raw.get("sentiment") or raw.get("sentiment_score")
        try:
            sent = float(sent) if sent is not None else None
        except Exception:
            sent = None
        return ReviewData(
            company_id=company_id,
            author_name=str(author)[:255],
            rating=float(rating),
            text=str(text or ""),
            review_time=dt,
            profile_photo_url=str(profile or ""),
            external_review_id=str(external_id) if external_id is not None else None,
            source_platform=self.source_platform,
            sentiment_score=sent,
            additional_fields={k: v for k, v in raw.items() if k not in {
                "author_name", "text", "rating", "date", "time", "profile_photo_url",
                "google_review_id", "review_id", "id", "sentiment", "sentiment_score"
            }},
        )


# ──────────────────────────────────────────────────────────────────────────────
# Fetch + ingest
# ──────────────────────────────────────────────────────────────────────────────
async def fetch_entity_reviews(client: Any, entity: Union[str, Dict[str, Any]], max_reviews: Optional[int] = None) -> List[Dict[str, Any]]:
    """Delegate to the provided async client to fetch raw reviews JSON for an entity.
    The entity can be a place_id or a dict containing place_id/name/etc.
    """
    if not hasattr(client, "fetch_reviews"):
        logger.warning("Reviews client missing fetch_reviews(entity, max_reviews) method.")
        return []
    try:
        return await client.fetch_reviews(entity, max_reviews=max_reviews)
    except Exception as ex:
        logger.warning("fetch_entity_reviews failed: %s", ex)
        return []


async def ingest_company_reviews(client: Any, company: Any, start: Optional[datetime] = None, end: Optional[datetime] = None, max_reviews: Optional[int] = None, source_platform: str = "Google") -> CompanyReviews:
    """Fetch, normalize, and filter reviews for a single company. Returns CompanyReviews.
    This does not write to DB; see run_batch_review_ingestion for persistence.
    """
    cid = int(getattr(company, "id", company.get("id") if isinstance(company, dict) else 0))
    service = OutscraperReviewsService(source_platform=source_platform)
    raw = await fetch_entity_reviews(client, company, max_reviews=max_reviews)
    if not raw:
        logger.warning("No reviews fetched for company %s", cid)
    out = CompanyReviews(company_id=cid)
    for r in raw:
        rd = service.normalize(r, company_id=cid)
        if not rd:
            continue
        if start and rd.review_time.date() < start.date():
            continue
        if end and rd.review_time.date() > end.date():
            continue
        out.reviews.append(rd)
    return out


async def ingest_multi_company_reviews(client: Any, entities: Iterable[Any], start: Optional[datetime] = None, end: Optional[datetime] = None, max_reviews: Optional[int] = None, source_platform: str = "Google") -> Dict[str, CompanyReviews]:
    """Fetch reviews for multiple entities. Keys are str(entity_id or place_id)."""
    result: Dict[str, CompanyReviews] = {}
    for ent in entities:
        try:
            cid = str(getattr(ent, "id", ent.get("id") if isinstance(ent, dict) else ent))
        except Exception:
            cid = str(ent)
        result[cid] = await ingest_company_reviews(client, ent, start=start, end=end, max_reviews=max_reviews, source_platform=source_platform)
    return result


async def run_batch_review_ingestion(client: Any, entities: Iterable[Any], start: Optional[datetime] = None, end: Optional[datetime] = None, max_reviews: Optional[int] = None, source_platform: str = "Google") -> Dict[str, Any]:
    """Legacy-compatible: fetch and write to DB, avoiding duplicates via external_review_id or composite key.
    Returns summary dict with counts per company.
    """
    summary: Dict[str, Any] = {"companies": []}
    for ent in entities:
        try:
            cid_int = int(getattr(ent, "id", ent.get("id") if isinstance(ent, dict) else ent))
        except Exception:
            continue
        crevs = await ingest_company_reviews(client, ent, start=start, end=end, max_reviews=max_reviews, source_platform=source_platform)
        new_count = 0
        async with get_session() as session:
            for rd in crevs.reviews:
                exists_q = None
                if rd.external_review_id:
                    exists_q = select(Review.id).where(and_(Review.company_id == cid_int, Review.external_review_id == rd.external_review_id)).limit(1)
                else:
                    exists_q = select(Review.id).where(and_(
                        Review.company_id == cid_int,
                        Review.author_name == rd.author_name,
                        Review.google_review_time.cast(Review.google_review_time.type) == rd.review_time
                    ))
                exists = (await session.execute(exists_q)).first()
                if exists:
                    continue
                obj = Review(
                    company_id=cid_int,
                    author_name=rd.author_name,
                    rating=float(rd.rating or 0.0),
                    text=rd.text,
                    google_review_time=rd.review_time,
                    profile_photo_url=rd.profile_photo_url,
                    external_review_id=rd.external_review_id,
                    source_platform=rd.source_platform,
                    sentiment_score=rd.sentiment_score,
                )
                session.add(obj)
                new_count += 1
            await session.commit()
        logger.info("Committed %s new reviews for company %s", new_count, cid_int)
        summary["companies"].append({"company_id": cid_int, "fetched": len(crevs.reviews), "saved": new_count})
    return summary


# ──────────────────────────────────────────────────────────────────────────────
# GOOGLE API KEY PLACEHOLDER
# ──────────────────────────────────────────────────────────────────────────────
# Insert your Google API key here and reference it in the client that fetches reviews.
# Example:
# GOOGLE_API_KEY = "YOUR_GOOGLE_API_KEY_HERE"
# Use this key in your Outscraper or Google client initialization.
