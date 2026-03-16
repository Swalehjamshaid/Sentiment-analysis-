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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.google_reviews")


# ───────────────────────────────────────────────
# DATACLASSES
# ───────────────────────────────────────────────

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
    def avg_rating(self) -> float:
        if not self.reviews:
            return 0.0
        return round(sum(r.rating for r in self.reviews) / len(self.reviews), 2)


# ───────────────────────────────────────────────
# HELPERS
# ───────────────────────────────────────────────

def _coerce_datetime(value: Any) -> Optional[datetime]:
    """Parse timestamps from Outscraper."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)

    if isinstance(value, (int, float)):
        if value > 10_000_000_000:
            return datetime.utcfromtimestamp(value / 1000.0)
        return datetime.utcfromtimestamp(value)

    if isinstance(value, str):
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
        ]
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


def _sentiment_from_rating(rating: float) -> float:
    """1–5 star → -1 to +1."""
    rating = max(1.0, min(5.0, rating))
    return round((rating - 3.0) / 2.0, 2)


def _stable_hash(author: str, text: str, dt: datetime) -> str:
    raw = f"{author.lower().strip()}|{text.strip()}|{dt.isoformat()}"
    return hashlib.md5(raw.encode()).hexdigest()


# ───────────────────────────────────────────────
# MAIN NORMALIZATION
# ───────────────────────────────────────────────

class OutscraperReviewsService:
    """Convert Outscraper raw payload → ReviewData objects."""

    def __init__(self, platform: str = "Google"):
        self.platform = platform

    def normalize(self, raw: Dict[str, Any], company_id: int) -> Optional[ReviewData]:
        if not raw:
            return None

        author = raw.get("author_name") or raw.get("author_title") or "Anonymous"
        text = raw.get("review_text") or raw.get("text") or ""
        rating = _coerce_rating(raw.get("review_rating") or raw.get("rating"))

        ts = raw.get("review_timestamp") or raw.get("time") or raw.get("review_datetime_utc")
        dt = _coerce_datetime(ts) or datetime.utcnow()

        profile = raw.get("author_image") or raw.get("profile_photo_url") or ""

        # Unique id
        external_id = (
            raw.get("review_id")
            or raw.get("google_review_id")
            or _stable_hash(author, text, dt)
        )

        return ReviewData(
            company_id=company_id,
            author_name=str(author)[:255],
            rating=rating,
            text=text,
            review_time=dt,
            profile_photo_url=profile,
            external_review_id=external_id,
            source_platform=self.platform,
            sentiment_score=_sentiment_from_rating(rating),
        )


# ───────────────────────────────────────────────
# INGESTION ENGINE
# ───────────────────────────────────────────────

async def run_batch_review_ingestion(
    client: Any,
    companies: Iterable[Any],
    *,
    session: AsyncSession,
    max_reviews: int = 200,
    source_platform: str = "Google",
) -> Dict[str, Any]:

    summary = {"total_saved": 0, "companies": []}
    normalizer = OutscraperReviewsService(platform=source_platform)

    for company in companies:
        cid = int(company.id)
        saved_count = 0

        try:
            logger.info(f"➡ Fetching reviews for company {cid}…")

            if asyncio.iscoroutinefunction(getattr(client, "fetch_reviews", None)):
                raw = await client.fetch_reviews(company, max_reviews=max_reviews)
            else:
                raw = await asyncio.to_thread(client.fetch_reviews, company, max_reviews=max_reviews)

            raw_list = raw if isinstance(raw, list) else [raw]

        except Exception as e:
            logger.error(f"❌ Failed to fetch reviews for {cid}: {e}")
            summary["companies"].append({"company_id": cid, "saved": 0, "error": str(e)})
            continue

        # Normalize all reviews
        normalized = []
        for block in raw_list:
            reviews_data = block.get("data") or block.get("reviews") or block
            if isinstance(reviews_data, list):
                for r in reviews_data:
                    nd = normalizer.normalize(r, cid)
                    if nd:
                        normalized.append(nd)

        # Preload existing IDs
        incoming_ids = [n.external_review_id for n in normalized]
        res = await session.execute(
            select(Review.google_review_id).where(
                and_(Review.company_id == cid, Review.google_review_id.in_(incoming_ids))
            )
        )
        existing_ids = set(res.scalars().all())

        # Insert new
        for item in normalized:
            if item.external_review_id in existing_ids:
                continue

            new_review = Review(
                company_id=cid,
                google_review_id=item.external_review_id,
                author_name=item.author_name,
                rating=item.rating,
                text=item.text,
                google_review_time=item.review_time,
                sentiment_score=item.sentiment_score,
                profile_photo_url=item.profile_photo_url,
            )
            session.add(new_review)
            saved_count += 1

        if saved_count > 0:
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                logger.warning(f"⚠ IntegrityError for company {cid} — likely duplicates.")
                saved_count = 0

        summary["total_saved"] += saved_count
        summary["companies"].append({"company_id": cid, "saved": saved_count})

    logger.info("✔ Batch ingestion completed.")
    return summary
