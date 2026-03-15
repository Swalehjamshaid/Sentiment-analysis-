# filename: app/services/google_reviews.py
from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.models import Review

# ──────────────────────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.google_reviews")


# ──────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────
@dataclass
class ReviewData:
    """Normalized single review."""

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
    """Collection of reviews for a company."""

    company_id: int
    reviews: List[ReviewData] = field(default_factory=list)

    @property
    def avg_rating(self) -> float:
        if not self.reviews:
            return 0.0
        return round(sum(r.rating for r in self.reviews) / len(self.reviews), 2)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
def _coerce_datetime(value: Any) -> Optional[datetime]:
    """Universal parser for timestamps or strings (naive UTC)."""
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
    if r is None:
        return 0.0
    try:
        r = max(1.0, min(5.0, float(r)))
        return round((r - 3.0) / 2.0, 2)
    except Exception:
        return 0.0


def _stable_hash_id(company_id: int, author: str, text: str, dt: datetime) -> str:
    """Stable MD5 for deduplication."""
    a = (author or "").strip().lower()
    t = " ".join((text or "").split())
    base = f"{company_id}|{a}|{t}|{dt.isoformat()}"
    return hashlib.md5(base.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────────────────────────
# Outscraper Review Service
# ──────────────────────────────────────────────────────────────
class OutscraperReviewsService:
    """Normalize raw scraper data into ReviewData objects."""

    def __init__(self, source_platform: str = "Google") -> None:
        self.source_platform = source_platform

    def normalize(self, raw: Dict[str, Any], company_id: int) -> Optional[ReviewData]:
        if not raw:
            return None

        author = raw.get("author_name") or raw.get("author_title") or "Anonymous"
        text = raw.get("review_text") or raw.get("text") or ""
        rating = _coerce_rating(raw.get("review_rating") or raw.get("rating"))

        when = raw.get("review_timestamp") or raw.get("time") or raw.get("review_datetime_utc")
        dt = _coerce_datetime(when)
        time_inferred = False
        if not dt:
            logger.warning("Unparseable review time; using utcnow() for company %s", company_id)
            dt = datetime.utcnow()
            time_inferred = True

        profile = raw.get("author_image") or raw.get("profile_photo_url") or ""
        external_id = (
            raw.get("review_id")
            or raw.get("google_review_id")
            or _stable_hash_id(company_id, author, text, dt)
        )

        sent = raw.get("sentiment_score")
        return ReviewData(
            company_id=company_id,
            author_name=str(author)[:255],
            rating=rating,
            text=str(text),
            review_time=dt,
            profile_photo_url=str(profile),
            external_review_id=str(external_id),
            source_platform=self.source_platform,
            sentiment_score=float(sent) if sent is not None else _sentiment_from_rating(rating),
            additional_fields={"time_inferred": time_inferred},
        )


# ──────────────────────────────────────────────────────────────
# Main ingestion engine
# ──────────────────────────────────────────────────────────────
async def run_batch_review_ingestion(
    client: Any,
    entities: Iterable[Any],
    *,
    session: AsyncSession,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    max_reviews: Optional[int] = None,
    source_platform: str = "Google",
) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"total_saved": 0, "companies": []}
    service = OutscraperReviewsService(source_platform=source_platform)

    for ent in entities:
        cid_int = int(getattr(ent, "id", 0))
        new_count = 0
        try:
            logger.info("Fetching reviews for company %s (max=%s)...", cid_int, max_reviews)
            if asyncio.iscoroutinefunction(getattr(client, "fetch_reviews", None)):
                raw_reviews = await client.fetch_reviews(ent, max_reviews=max_reviews)
            else:
                raw_reviews = await asyncio.to_thread(client.fetch_reviews, ent, max_reviews=max_reviews)
            raw_reviews = raw_reviews or []
            logger.info("Fetched %d reviews for company %s", len(raw_reviews), cid_int)
        except Exception as ex:
            logger.error("Failed fetching reviews for %s: %s", cid_int, ex)
            summary["companies"].append({"company_id": cid_int, "saved": 0, "error": str(ex)})
            continue

        normalized: List[ReviewData] = []
        for raw in raw_reviews:
            rd = service.normalize(raw, company_id=cid_int)
            if not rd:
                continue
            if start and rd.review_time < start:
                continue
            if end and rd.review_time > end:
                continue
            normalized.append(rd)

        if not normalized:
            summary["companies"].append({"company_id": cid_int, "saved": 0})
            logger.info("No reviews to save for company %s after filtering", cid_int)
            continue

        incoming_ids = [r.external_review_id for r in normalized if r.external_review_id]
        existing_ids: set[str] = set()
        if incoming_ids:
            res = await session.execute(
                select(Review.google_review_id).where(and_(Review.company_id == cid_int, Review.google_review_id.in_(incoming_ids)))
            )
            existing_ids = set(res.scalars().all())

        for rd in normalized:
            if rd.external_review_id in existing_ids:
                continue

            new_review = Review(
                company_id=cid_int,
                google_review_id=(rd.external_review_id or "")[:255],
                author_name=(rd.author_name or "")[:255],
                rating=rd.rating,
                text=rd.text,
                google_review_time=rd.review_time,
                sentiment_score=rd.sentiment_score,
                profile_photo_url=rd.profile_photo_url,
            )
            session.add(new_review)
            new_count += 1

        try:
            if new_count > 0:
                await session.commit()
                logger.info("Committed %d reviews for company %s", new_count, cid_int)
        except IntegrityError as ie:
            await session.rollback()
            logger.warning("IntegrityError committing reviews for %s: %s", cid_int, ie)
            new_count = 0
        except Exception as e:
            await session.rollback()
            logger.error("Failed to commit reviews for company %s: %s", cid_int, e)
            new_count = 0

        summary["total_saved"] += new_count
        summary["companies"].append({"company_id": cid_int, "saved": new_count})

    logger.info("Batch ingestion complete: %s", summary)
    return summary
