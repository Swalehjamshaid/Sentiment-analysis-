# filename: review_saas/app/services/google_reviews.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import Counter

# --- DATABASE INTEGRATION ---
from sqlalchemy import select, and_
from app.core.db import get_session
from app.core.models import Review
# ----------------------------

logger = logging.getLogger("app.services.google_reviews")
logger.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────

@dataclass
class ReviewData:
    """Standardized internal data structure for a single review."""
    review_id: str
    author_name: str
    rating: float
    text: str
    time_created: datetime
    sentiment: Optional[str] = None
    review_title: Optional[str] = None
    helpful_votes: Optional[int] = 0
    source_platform: Optional[str] = None
    competitor_name: Optional[str] = None
    additional_fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompanyReviews:
    """Container for a batch of reviews belonging to a company."""
    company_id: str
    reviews: List[ReviewData] = field(default_factory=list)

    def add_review(self, review: ReviewData):
        self.reviews.append(review)

    def rating_summary(self) -> Dict[str, float]:
        """Calculates average, min, max, and count for dashboard KPIs."""
        if not self.reviews:
            return {"average": 0.0, "min": 0.0, "max": 0.0, "count": 0}
        ratings = [float(r.rating or 0.0) for r in self.reviews]
        return {
            "average": sum(ratings) / len(ratings),
            "min": min(ratings),
            "max": max(ratings),
            "count": len(ratings),
        }

    def rating_distribution(self) -> Dict[int, int]:
        """Calculates 1-5 star frequency for the dashboard histogram."""
        def as_star(v: float) -> int:
            try:
                s = int(round(float(v)))
            except Exception:
                s = 0
            return max(1, min(5, s)) if s else 0

        dist = Counter(as_star(r.rating) for r in self.reviews if r.rating is not None)
        return {i: dist.get(i, 0) for i in range(1, 6)}


# ─────────────────────────────────────────────────────────────
# Service Layer
# ─────────────────────────────────────────────────────────────

class OutscraperReviewsService:
    """Service for interacting with the Outscraper API Client."""

    PAGE_SIZE = 100

    def __init__(self, api_client: Any):
        self.client = api_client

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime:
        """Ensures timestamps are converted to naive datetime."""
        if not value:
            return datetime.now()
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value))
            except:
                pass
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt.replace(tzinfo=None)
            except:
                try:
                    return datetime.strptime(value, "%Y-%m-%d")
                except:
                    pass
        return datetime.now()

    def _to_review_data(self, row: Dict[str, Any], competitor_name: Optional[str] = None) -> Optional[ReviewData]:
        """Maps a raw Outscraper JSON row to a ReviewData object."""
        r_id = row.get("review_id") or row.get("id") or row.get("google_review_id")
        if not r_id:
            return None

        return ReviewData(
            review_id=str(r_id),
            author_name=str(row.get("author_name") or row.get("author") or "Anonymous"),
            rating=float(row.get("rating") or row.get("stars") or 0.0),
            text=str(row.get("text") or row.get("review_text") or row.get("content") or ""),
            time_created=self._coerce_datetime(row.get("timestamp") or row.get("time") or row.get("date")),
            competitor_name=competitor_name,
            source_platform=str(row.get("source") or row.get("platform") or "Google"),
            additional_fields=row
        )

    async def fetch_entity_reviews(self, place_id: str, limit: int = 100, competitor_name: Optional[str] = None) -> List[ReviewData]:
        """Fetches and maps reviews for a single place_id."""
        response = await self.client.get_reviews(place_id=place_id, limit=limit)
        raw_list = response.get("reviews", [])
        if not raw_list:
            logger.warning(f"⚠️ No reviews returned for Place ID: {place_id}")
            return []
        logger.info(f"✅ Mapping {len(raw_list)} reviews for {competitor_name or 'Primary Company'}")
        return [self._to_review_data(r, competitor_name) for r in raw_list if r]


# ─────────────────────────────────────────────────────────────
# Persistence Layer
# ─────────────────────────────────────────────────────────────

async def run_batch_review_ingestion(api_client: Any, primary_company_id: int, entities: List[Dict[str, Any] | str]):
    """Fetches reviews and saves them to the database."""
    logger.info(f"🚀 Batch Ingestion Triggered for Company ID: {primary_company_id}")
    service = OutscraperReviewsService(api_client)
    
    processed_entities = []
    for ent in entities:
        if isinstance(ent, str):
            processed_entities.append({"place_id": ent, "name": None})
        else:
            processed_entities.append({
                "place_id": ent.get("place_id"),
                "name": ent.get("name") or ent.get("competitor_name")
            })

    async with get_session() as session:
        total_new_reviews = 0
        for ent in processed_entities:
            pid = ent['place_id']
            c_name = ent['name']

            # Fetch reviews
            fetched_reviews = await service.fetch_entity_reviews(place_id=pid, limit=500, competitor_name=c_name)
            
            # Save reviews to DB
            for rd in fetched_reviews:
                if not rd:
                    continue

                stmt = select(Review).where(and_(
                    Review.company_id == primary_company_id,
                    Review.google_review_id == rd.review_id
                ))
                existing = await session.execute(stmt)
                if existing.scalar_one_or_none():
                    continue

                db_review = Review(
                    company_id=primary_company_id,
                    google_review_id=rd.review_id,
                    author_name=rd.author_name,
                    rating=rd.rating,
                    text=rd.text,
                    google_review_time=rd.time_created,
                    competitor_name=rd.competitor_name,
                    source_platform=rd.source_platform
                )
                session.add(db_review)
                total_new_reviews += 1
        
        if total_new_reviews > 0:
            await session.commit()
            logger.info(f"✨ Successfully committed {total_new_reviews} new reviews to DB.")
        else:
            logger.info("ℹ️ Sync complete. No new reviews were found.")

async def ingest_multi_company_reviews(primary_company_id: int, entities: List[Dict[str, Any] | str], api_client: Any) -> int:
    """Wrapper to run ingestion and return total count saved."""
    return await run_batch_review_ingestion(api_client, primary_company_id, entities)
