# filename: app/services/google_reviews.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Union

import httpx
from sqlalchemy import and_, select

from app.core.db import get_session
from app.core.models import Review

logger = logging.getLogger("app.google_reviews")

OUTSCRAPER_ENDPOINT = "https://api.app.outscraper.com/maps/reviews-v3"


# ─────────────────────────────────────────────────────────────
# Data Models
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


# ─────────────────────────────────────────────────────────────
# Normalization
# ─────────────────────────────────────────────────────────────

def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.replace(tzinfo=None)

    try:
        if isinstance(value, (int, float)):
            return datetime.utcfromtimestamp(float(value))
    except Exception:
        pass

    if isinstance(value, str):
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(value, fmt)
            except Exception:
                continue

    return None


class OutscraperReviewsService:

    def __init__(self, api_key: str, source_platform: str = "Google"):
        self.api_key = api_key
        self.source_platform = source_platform

    async def fetch_reviews(self, place_id: str, limit: int = 100) -> List[Dict]:

        params = {
            "query": place_id,
            "limit": limit,
            "async": "false"
        }

        headers = {
            "X-API-KEY": self.api_key
        }

        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.get(OUTSCRAPER_ENDPOINT, params=params, headers=headers)

        if r.status_code != 200:
            logger.error("❌ Outscraper API Error %s: %s", r.status_code, r.text)
            return []

        data = r.json()

        if not isinstance(data, list):
            return []

        reviews: List[Dict] = []

        for block in data:
            reviews.extend(block.get("reviews_data", []))

        logger.info("Fetched %s raw reviews", len(reviews))
        return reviews

    def normalize(self, raw: Dict[str, Any], company_id: int) -> Optional[ReviewData]:

        author = raw.get("author_title") or raw.get("author_name") or "Anonymous"
        rating = raw.get("review_rating") or raw.get("rating") or 0
        text = raw.get("review_text") or raw.get("text") or ""
        review_time = raw.get("review_datetime_utc")

        dt = _coerce_datetime(review_time) or datetime.utcnow()

        external_id = raw.get("review_id")

        return ReviewData(
            company_id=company_id,
            author_name=str(author),
            rating=float(rating),
            text=str(text),
            review_time=dt,
            profile_photo_url=str(raw.get("author_image", "")),
            external_review_id=str(external_id) if external_id else None,
            source_platform=self.source_platform,
        )


# ─────────────────────────────────────────────────────────────
# Fetch + Normalize
# ─────────────────────────────────────────────────────────────

async def ingest_company_reviews(
    client: Any,
    company: Any,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    max_reviews: Optional[int] = None,
    source_platform: str = "Google",
) -> CompanyReviews:

    cid = int(getattr(company, "id"))

    place_id = getattr(company, "google_place_id", None)

    service = OutscraperReviewsService(client.api_key)

    raw_reviews = await service.fetch_reviews(place_id, max_reviews or 100)

    result = CompanyReviews(company_id=cid)

    for r in raw_reviews:

        rd = service.normalize(r, company_id=cid)

        if not rd:
            continue

        if start and rd.review_time < start:
            continue

        if end and rd.review_time > end:
            continue

        result.reviews.append(rd)

    logger.info("Normalized %s reviews for company %s", len(result.reviews), cid)

    return result


# ─────────────────────────────────────────────────────────────
# Save to Database
# ─────────────────────────────────────────────────────────────

async def run_batch_review_ingestion(
    client: Any,
    entities: Iterable[Any],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    max_reviews: Optional[int] = None,
    source_platform: str = "Google",
):

    summary = {"companies": []}

    for ent in entities:

        cid = int(getattr(ent, "id"))

        company_reviews = await ingest_company_reviews(
            client,
            ent,
            start=start,
            end=end,
            max_reviews=max_reviews,
        )

        new_count = 0

        async with get_session() as session:

            for rd in company_reviews.reviews:

                q = select(Review.id).where(
                    and_(
                        Review.company_id == cid,
                        Review.external_review_id == rd.external_review_id,
                    )
                )

                exists = (await session.execute(q)).first()

                if exists:
                    continue

                session.add(
                    Review(
                        company_id=cid,
                        author_name=rd.author_name,
                        rating=rd.rating,
                        text=rd.text,
                        google_review_time=rd.review_time,
                        profile_photo_url=rd.profile_photo_url,
                        external_review_id=rd.external_review_id,
                        source_platform=rd.source_platform,
                    )
                )

                new_count += 1

            await session.commit()

        logger.info("Committed %s new reviews for company %s", new_count, cid)

        summary["companies"].append(
            {
                "company_id": cid,
                "fetched": len(company_reviews.reviews),
                "saved": new_count,
            }
        )

    return summary
