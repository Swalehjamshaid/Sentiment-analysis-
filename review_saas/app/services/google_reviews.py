# filename: review_saas/app/services/google_reviews.py

from __future__ import annotations

import os
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import get_session
from app.core.models import Review

# ──────────────────────────────────────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.google_reviews")

# ──────────────────────────────────────────────────────────────────────────────
# DATABASE CONFIGURATION & ASYNC DRIVER FIX
# ──────────────────────────────────────────────────────────────────────────────
def get_async_url() -> str:
    """Ensure SQLAlchemy asyncpg URL and fallback if DATABASE_URL is missing."""
    url = os.getenv("DATABASE_URL", "")
    if not url:
        return "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

DATABASE_URL = get_async_url()

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True
)

# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _coerce_datetime(value: Any) -> Optional[datetime]:
    """Universal parser for timestamps or strings."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        if isinstance(value, (int, float)):
            if float(value) > 10_000_000_000:  # ms
                return datetime.utcfromtimestamp(float(value) / 1000.0)
            return datetime.utcfromtimestamp(float(value))
    except Exception:
        pass
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except Exception:
                continue
    return None

def _sentiment_from_rating(r: Optional[float]) -> float:
    """Convert 1-5 star rating to -1.0 to 1.0 sentiment."""
    if r is None: return 0.0
    try:
        r = max(1.0, min(5.0, float(r)))
        return round((r - 3.0) / 2.0, 2)
    except Exception:
        return 0.0

def _stable_hash_id(author: str, text: str, dt: datetime) -> str:
    """Generate stable ID if no external ID."""
    base = f"{author}{text}{dt.isoformat()}"
    return hashlib.md5(base.encode()).hexdigest()

# ──────────────────────────────────────────────────────────────────────────────
# Outscraper Review Service
# ──────────────────────────────────────────────────────────────────────────────
class OutscraperReviewsService:
    """Normalize raw scraper data into ReviewData."""
    def __init__(self, source_platform: str = "Google") -> None:
        self.source_platform = source_platform

    def normalize(self, raw: Dict[str, Any], company_id: int) -> Optional[ReviewData]:
        if not raw:
            return None
        author = raw.get("author_name") or raw.get("author_title") or "Anonymous"
        text = raw.get("review_text") or raw.get("text") or ""
        rating = float(raw.get("review_rating") or raw.get("rating") or 0.0)
        when = raw.get("review_timestamp") or raw.get("time") or raw.get("review_datetime_utc")
        dt = _coerce_datetime(when) or datetime.utcnow()
        profile = raw.get("author_image") or raw.get("profile_photo_url") or ""
        external_id = raw.get("review_id") or raw.get("google_review_id") or _stable_hash_id(author, text, dt)
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
            sentiment_score=float(sent) if sent is not None else _sentiment_from_rating(rating)
        )

# ──────────────────────────────────────────────────────────────────────────────
# Main ingestion engine
# ──────────────────────────────────────────────────────────────────────────────
async def run_batch_review_ingestion(
    client: Any,
    entities: Iterable[Any],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    max_reviews: Optional[int] = None,
    source_platform: str = "Google"
) -> Dict[str, Any]:
    """Fetch from Outscraper, dedupe, save to PostgreSQL, return summary."""
    summary = {"total_saved": 0, "companies": []}
    service = OutscraperReviewsService(source_platform=source_platform)

    for ent in entities:
        try:
            cid_int = int(getattr(ent, "id", 0))
            logger.info(f"Fetching reviews for company {cid_int}...")
            
            # Support async or sync client
            if asyncio.iscoroutinefunction(client.fetch_reviews):
                raw_reviews = await client.fetch_reviews(ent, max_reviews=max_reviews)
            else:
                import asyncio
                raw_reviews = await asyncio.to_thread(client.fetch_reviews, ent, max_reviews=max_reviews)
            
            logger.info(f"Fetched {len(raw_reviews)} raw reviews for company {cid_int}")
            logger.debug(f"Raw review data: {raw_reviews}")
        except Exception as ex:
            logger.error(f"Ingestion failed for entity {ent}: {ex}")
            continue

        new_count = 0
        async with get_session() as session:
            for raw in raw_reviews:
                rd = service.normalize(raw, company_id=cid_int)
                if not rd:
                    logger.warning(f"Skipping empty/invalid review: {raw}")
                    continue

                # Date filter
                if start and rd.review_time < start:
                    continue
                if end and rd.review_time > end:
                    continue

                # Deduplication check
                exists_q = select(Review.id).where(
                    and_(Review.company_id == cid_int, Review.google_review_id == rd.external_review_id)
                ).limit(1)
                exists_res = await session.execute(exists_q)
                if exists_res.first():
                    logger.debug(f"Duplicate review skipped: {rd.external_review_id}")
                    continue

                # Add review
                session.add(Review(
                    company_id=cid_int,
                    google_review_id=rd.external_review_id,
                    author_name=rd.author_name,
                    rating=rd.rating,
                    text=rd.text,
                    google_review_time=rd.review_time,
                    sentiment_score=rd.sentiment_score,
                    profile_photo_url=rd.profile_photo_url
                ))
                logger.info(f"Adding review {rd.external_review_id} for company {cid_int}")
                new_count += 1

            try:
                await session.commit()
                logger.info(f"Saved {new_count} new reviews for company {cid_int}")
            except Exception as e:
                logger.error(f"Failed to commit reviews for company {cid_int}: {e}")

        summary["total_saved"] += new_count
        summary["companies"].append({"company_id": cid_int, "saved": new_count})

    logger.info(f"Batch ingestion complete: {summary}")
    return summary
