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

# ─────────────────────────────────────────────────────────────
# Normalized Review Data Models
# These models represent normalized review data before
# being written into PostgreSQL.
# They are used internally by the service layer.
# ─────────────────────────────────────────────────────────────

@dataclass
class ReviewData:
    company_id: int
    author_name: str
    rating: float
    text: str
    review_time: datetime
    profile_photo_url: str = ""
    external_review_id: Optional[str] = None
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
        return round(sum(float(r.rating or 0) for r in self.reviews) / len(self.reviews), 3)

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
                if 1 <= rr <= 5:
                    dist[rr] += 1
            except Exception:
                continue
        return dist


# ─────────────────────────────────────────────────────────────
# Datetime Normalization
# Converts timestamps, ISO strings, or datetime objects
# into naive UTC datetime values compatible with DB storage.
# ─────────────────────────────────────────────────────────────

def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.replace(tzinfo=None)

    try:
        if isinstance(value, (int, float)):
            return datetime.utcfromtimestamp(
                float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
            )
    except Exception:
        pass

    if isinstance(value, str):
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%fZ",
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


# ─────────────────────────────────────────────────────────────
# Review Normalization Service
# Converts raw external review JSON (Outscraper/Google)
# into the internal ReviewData structure used by the system.
# ─────────────────────────────────────────────────────────────

class OutscraperReviewsService:

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

        ignore = {
            "author_name", "text", "rating", "date", "time",
            "profile_photo_url", "google_review_id",
            "review_id", "id", "sentiment", "sentiment_score"
        }

        return ReviewData(
            company_id=company_id,
            author_name=str(author)[:255],
            rating=float(rating),
            text=str(text),
            review_time=dt,
            profile_photo_url=str(profile),
            external_review_id=str(external_id) if external_id else None,
            source_platform=self.source_platform,
            sentiment_score=sent,
            additional_fields={k: v for k, v in raw.items() if k not in ignore},
        )


# ─────────────────────────────────────────────────────────────
# Review Fetching
# Delegates the fetching process to the configured
# external reviews client (Outscraper or similar).
# ─────────────────────────────────────────────────────────────

async def fetch_entity_reviews(
    client: Any,
    entity: Union[str, Dict[str, Any]],
    max_reviews: Optional[int] = None
) -> List[Dict[str, Any]]:

    if not hasattr(client, "fetch_reviews"):
        logger.warning("Reviews client missing fetch_reviews method.")
        return []

    try:
        return await client.fetch_reviews(entity, max_reviews=max_reviews)
    except Exception as ex:
        logger.warning("fetch_entity_reviews failed: %s", ex)
        return []


# ─────────────────────────────────────────────────────────────
# Company Review Ingestion (No DB Write)
# Fetches and normalizes reviews for a company.
# Used by ingestion workflows.
# ─────────────────────────────────────────────────────────────

async def ingest_company_reviews(
    client: Any,
    company: Any,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    max_reviews: Optional[int] = None,
    source_platform: str = "Google"
) -> CompanyReviews:

    cid = int(getattr(company, "id", company.get("id") if isinstance(company, dict) else 0))
    raw_reviews = await fetch_entity_reviews(client, company, max_reviews)

    service = OutscraperReviewsService(source_platform)
    result = CompanyReviews(company_id=cid)

    for raw in raw_reviews:
        rd = service.normalize(raw, cid)
        if not rd:
            continue

        if start and rd.review_time < start:
            continue
        if end and rd.review_time > end:
            continue

        result.reviews.append(rd)

    if not result.reviews:
        logger.warning("No reviews fetched for company %s", cid)

    return result


# ─────────────────────────────────────────────────────────────
# Multi-company review ingestion helper
# ─────────────────────────────────────────────────────────────

async def ingest_multi_company_reviews(
    client: Any,
    entities: Iterable[Any],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    max_reviews: Optional[int] = None,
    source_platform: str = "Google"
) -> Dict[str, CompanyReviews]:

    results: Dict[str, CompanyReviews] = {}

    for ent in entities:
        try:
            key = str(getattr(ent, "id", ent.get("id") if isinstance(ent, dict) else ent))
        except Exception:
            key = str(ent)

        results[key] = await ingest_company_reviews(
            client, ent, start=start, end=end, max_reviews=max_reviews, source_platform=source_platform
        )

    return results


# ─────────────────────────────────────────────────────────────
# Batch Review Ingestion (DB Write)
# Fetches reviews, normalizes them, and inserts them
# into PostgreSQL while preventing duplicates.
# ─────────────────────────────────────────────────────────────

async def run_batch_review_ingestion(
    client: Any,
    entities: Iterable[Any],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    max_reviews: Optional[int] = None,
    source_platform: str = "Google"
) -> Dict[str, Any]:

    summary: Dict[str, Any] = {"companies": []}

    for ent in entities:

        try:
            cid = int(getattr(ent, "id", ent.get("id") if isinstance(ent, dict) else ent))
        except Exception:
            continue

        company_reviews = await ingest_company_reviews(
            client, ent, start=start, end=end, max_reviews=max_reviews, source_platform=source_platform
        )

        inserted = 0

        async with get_session() as session:

            for r in company_reviews.reviews:

                if r.external_review_id:
                    q = select(Review.id).where(
                        and_(Review.company_id == cid, Review.external_review_id == r.external_review_id)
                    )
                else:
                    q = select(Review.id).where(
                        and_(
                            Review.company_id == cid,
                            Review.author_name == r.author_name,
                            Review.google_review_time == r.review_time,
                        )
                    )

                exists = (await session.execute(q)).first()
                if exists:
                    continue

                session.add(
                    Review(
                        company_id=cid,
                        author_name=r.author_name,
                        rating=float(r.rating or 0),
                        text=r.text,
                        google_review_time=r.review_time,
                        profile_photo_url=r.profile_photo_url,
                        external_review_id=r.external_review_id,
                        source_platform=r.source_platform,
                        sentiment_score=r.sentiment_score,
                    )
                )

                inserted += 1

            await session.commit()

        logger.info("Committed %s new reviews for company %s", inserted, cid)

        summary["companies"].append(
            {
                "company_id": cid,
                "fetched": len(company_reviews.reviews),
                "saved": inserted,
            }
        )

    return summary
