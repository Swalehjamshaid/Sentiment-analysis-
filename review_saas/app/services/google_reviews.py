# filename: review_saas/app/services/google_reviews.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import Counter

from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review

# -------------------------------
# Logger setup
# -------------------------------
logger = logging.getLogger("app.services.google_reviews")
logger.setLevel(logging.INFO)

# -------------------------------
# Data Models
# -------------------------------
@dataclass
class ReviewData:
    """Unified internal review representation."""
    review_id: str
    author_name: str
    rating: float
    text: str
    time_created: datetime
    sentiment: Optional[str] = None
    review_title: Optional[str] = None
    helpful_votes: int = 0
    source_platform: str = "Google"
    competitor_name: Optional[str] = None
    additional_fields: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CompanyReviews:
    """Container for a company's reviews."""
    company_id: str
    reviews: List[ReviewData] = field(default_factory=list)

    def add_review(self, review: ReviewData):
        self.reviews.append(review)

    def rating_summary(self) -> Dict[str, float]:
        if not self.reviews:
            return {"average": 0.0, "min": 0.0, "max": 0.0, "count": 0}
        vals = [float(r.rating or 0) for r in self.reviews]
        return {
            "average": sum(vals) / len(vals),
            "min": min(vals),
            "max": max(vals),
            "count": len(vals),
        }

    def rating_distribution(self) -> Dict[int, int]:
        def to_star(r):
            try:
                return max(1, min(5, int(round(float(r.rating)))))
            except:
                return 0
        counter = Counter(to_star(r) for r in self.reviews if r.rating)
        return {i: counter.get(i, 0) for i in range(1, 6)}

# -------------------------------
# Outscraper / Google Review Service
# -------------------------------
class OutscraperReviewsService:
    """Normalizes raw Outscraper/Google reviews into ReviewData."""

    def __init__(self, api_client: Any):
        self.client = api_client

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime:
        """Convert timestamps/ISO strings to naive datetime."""
        if not value:
            return datetime.now()
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value))
            except:
                return datetime.now()
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt.replace(tzinfo=None)
            except:
                pass
            try:
                return datetime.strptime(value, "%Y-%m-%d")
            except:
                pass
        return datetime.now()

    def _to_review_data(self, row: Dict[str, Any], competitor_name: Optional[str] = None) -> Optional[ReviewData]:
        r_id = row.get("review_id") or row.get("reviewId") or row.get("id") or row.get("google_review_id")
        if not r_id:
            return None
        return ReviewData(
            review_id=str(r_id),
            author_name=str(row.get("author_name") or row.get("author") or "Anonymous"),
            rating=float(row.get("rating") or row.get("stars") or 0.0),
            text=str(row.get("text") or row.get("review_text") or row.get("content") or ""),
            time_created=self._coerce_datetime(row.get("time") or row.get("timestamp") or row.get("date")),
            source_platform=str(row.get("source") or "Google"),
            competitor_name=competitor_name,
            additional_fields=row,
        )

    async def fetch_entity_reviews(self, place_id: str, limit: int = 200, competitor_name: Optional[str] = None) -> List[ReviewData]:
        response = await self.client.get_reviews(place_id=place_id, limit=limit)
        raw_list = response.get("reviews", [])
        if not raw_list:
            logger.warning(f"⚠️ No reviews found for {place_id}")
            return []
        out = []
        for row in raw_list:
            rd = self._to_review_data(row, competitor_name)
            if rd:
                out.append(rd)
        logger.info(f"Fetched {len(out)} reviews for {competitor_name or place_id}")
        return out

# -------------------------------
# Ingestion / Sync Functions
# -------------------------------
async def ingest_company_reviews(place_id: str, company_id: str, api_client: Any, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, max_reviews: int = 300) -> CompanyReviews:
    service = OutscraperReviewsService(api_client)
    data = CompanyReviews(company_id=str(company_id))
    rows = await service.fetch_entity_reviews(place_id, limit=max_reviews)
    filtered = [r for r in rows if (not start_date or r.time_created >= start_date) and (not end_date or r.time_created <= end_date)]
    data.reviews = filtered
    return data

async def ingest_multi_company_reviews(primary_company_id: str, entities: List[str | Dict[str, Any]], api_client: Any, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, max_reviews_per_entity: int = 200) -> Dict[str, CompanyReviews]:
    service = OutscraperReviewsService(api_client)
    results: Dict[str, CompanyReviews] = {}
    for ent in entities:
        if isinstance(ent, str):
            pid, cname = ent, None
        else:
            pid = ent.get("place_id")
            cname = ent.get("name") or ent.get("competitor_name")
        bucket = CompanyReviews(company_id=str(primary_company_id))
        rows = await service.fetch_entity_reviews(pid, limit=max_reviews_per_entity, competitor_name=cname)
        filtered = [r for r in rows if (not start_date or r.time_created >= start_date) and (not end_date or r.time_created <= end_date)]
        bucket.reviews = filtered
        results[pid] = bucket
    return results

# -------------------------------
# Legacy DB Write Path
# -------------------------------
async def run_batch_review_ingestion(api_client: Any, primary_company_id: int, entities: List[str | Dict[str, Any]]):
    logger.info(f"Running batch ingestion for company {primary_company_id}")
    service = OutscraperReviewsService(api_client)
    async with get_session() as session:
        total_new = 0
        for ent in entities:
            if isinstance(ent, str):
                pid, cname = ent, None
            else:
                pid = ent.get("place_id")
                cname = ent.get("name") or ent.get("competitor_name")
            rows = await service.fetch_entity_reviews(pid, limit=400, competitor_name=cname)
            for rd in rows:
                exists = await session.execute(select(Review.id).where(Review.company_id == primary_company_id, Review.google_review_id == rd.review_id))
                if exists.scalar():
                    continue
                item = Review(
                    company_id=primary_company_id,
                    google_review_id=rd.review_id,
                    author_name=rd.author_name,
                    rating=rd.rating,
                    text=rd.text,
                    google_review_time=rd.time_created,
                    competitor_name=rd.competitor_name,
                    source_platform=rd.source_platform,
                )
                session.add(item)
                total_new += 1
        if total_new:
            await session.commit()
        logger.info(f"Committed {total_new} new reviews")
    return total_new
