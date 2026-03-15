# filename: review_saas/app/services/google_reviews.py
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

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────
logger = logging.getLogger("app.google_reviews")


# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class ReviewData:
    """Normalized single review from any scraper/client."""
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
    """A collection of normalized reviews for a company."""
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
    """Parse common timestamp formats to naive UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)

    # Unix seconds / milliseconds
    try:
        if isinstance(value, (int, float)):
            v = float(value)
            if v > 10_000_000_000:  # milliseconds
                return datetime.utcfromtimestamp(v / 1000.0)
            return datetime.utcfromtimestamp(v)
    except Exception:
        pass

    # ISO / common string formats
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


def _sentiment_from_rating(r: Optional[float]) -> float:
    """Map 1–5 star rating to a rough sentiment in [-1, 1]."""
    if r is None:
        return 0.0
    try:
        r = max(1.0, min(5.0, float(r)))
        return round((r - 3.0) / 2.0, 2)
    except Exception:
        return 0.0


def _stable_hash_id(author: str, text: str, dt: datetime) -> str:
    """Generate a stable hash when the scraper does not provide a unique id."""
    base = f"{author}{text}{dt.isoformat()}"
    return hashlib.md5(base.encode()).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# Normalizer
# ──────────────────────────────────────────────────────────────────────────────
class OutscraperReviewsService:
    """Turns raw scraper dicts into our normalized ReviewData."""

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

        # Prefer explicit IDs, else fall back to a stable hash
        external_id = (
            raw.get("review_id")
            or raw.get("google_review_id")
            or _stable_hash_id(str(author), str(text), dt)
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
        )


# ──────────────────────────────────────────────────────────────────────────────
# Main ingestion (uses the SAME AsyncSession as FastAPI -> fixes “not saving”)
# ──────────────────────────────────────────────────────────────────────────────
async def run_batch_review_ingestion(
    client: Any,
    entities: Iterable[Any],
    *,
    session: AsyncSession,                 # ← REQUIRED: use app session (no separate engine)
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    max_reviews: Optional[int] = None,
    source_platform: str = "Google",
) -> Dict[str, Any]:
    """
    Fetch reviews via `client.fetch_reviews(entity, max_reviews=...)`,
    normalize, de-duplicate, and persist using the provided AsyncSession.

    Returns:
      {
        "total_saved": int,
        "total_fetched": int,
        "total_duplicates": int,
        "companies": [
          {"company_id": int, "fetched": int, "saved": int, "duplicates": int}
        ]
      }
    """
    service = OutscraperReviewsService(source_platform=source_platform)
    summary: Dict[str, Any] = {
        "total_saved": 0,
        "total_fetched": 0,
        "total_duplicates": 0,
        "companies": [],
    }

    for ent in entities:
        company_id = int(getattr(ent, "id", 0))
        company_saved = 0
        company_dupes = 0
        company_fetched = 0

        try:
            # Support both async & sync clients
            fetch_fn = getattr(client, "fetch_reviews", None)
            if fetch_fn is None:
                raise RuntimeError("Client does not expose fetch_reviews(...)")

            if asyncio.iscoroutinefunction(fetch_fn):
                raw_reviews = await fetch_fn(ent, max_reviews=max_reviews)
            else:
                raw_reviews = await asyncio.to_thread(fetch_fn, ent, max_reviews=max_reviews)

            raw_reviews = raw_reviews or []
            company_fetched = len(raw_reviews)
            summary["total_fetched"] += company_fetched
            logger.info(f"[Ingest] Fetched {company_fetched} raw reviews for company {company_id}")

        except Exception as ex:
            logger.exception(f"[Ingest] Fetch failed for company {company_id}: {ex}")
            summary["companies"].append(
                {"company_id": company_id, "fetched": 0, "saved": 0, "duplicates": 0, "error": str(ex)}
            )
            continue

        # Normalize + persist
        for raw in raw_reviews:
            rd = service.normalize(raw, company_id=company_id)
            if not rd:
                continue

            # Date window filter (inclusive)
            if start and rd.review_time < start:
                continue
            if end and rd.review_time > end:
                continue

            # De-dup using google_review_id (or stable hash fallback)
            exists_q = (
                select(Review.id)
                .where(and_(Review.company_id == company_id, Review.google_review_id == rd.external_review_id))
                .limit(1)
            )
            res = await session.execute(exists_q)
            if res.first():
                company_dupes += 1
                continue

            # Build ORM object (align fields with your Review model)
            obj = Review(
                company_id=company_id,
                google_review_id=rd.external_review_id,
                author_name=rd.author_name,
                rating=rd.rating,
                text=rd.text,
                google_review_time=rd.review_time,
                sentiment_score=rd.sentiment_score,
                profile_photo_url=rd.profile_photo_url,
            )
            session.add(obj)
            company_saved += 1

        # Commit batch for this company
        try:
            if company_saved > 0:
                await session.commit()
            else:
                # Ensure the session stays clean between entities
                await session.flush()
        except IntegrityError as ie:
            # If DB has a unique index on (company_id, google_review_id)
            await session.rollback()
            logger.warning(f"[Ingest] IntegrityError for company {company_id}: {ie}")
        except Exception as e:
            await session.rollback()
            logger.exception(f"[Ingest] Commit failed for company {company_id}: {e}")

        summary["total_saved"] += company_saved
        summary["total_duplicates"] += company_dupes
        summary["companies"].append(
            {"company_id": company_id, "fetched": company_fetched, "saved": company_saved, "duplicates": company_dupes}
        )

        logger.info(
            f"[Ingest] Company {company_id}: fetched={company_fetched}, saved={company_saved}, dupes={company_dupes}"
        )

    logger.info(f"[Ingest] Batch complete: {summary}")
    return summary
