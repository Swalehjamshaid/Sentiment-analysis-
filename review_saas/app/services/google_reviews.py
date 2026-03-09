# filename: app/services/google_reviews.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

# --- DATABASE INTEGRATION ---
from sqlalchemy import select, and_
from app.core.db import get_session
from app.core.models import Review 
# ----------------------------

logger = logging.getLogger("app.services.google_reviews")
logger.setLevel(logging.INFO)

# ──────────────────────────────────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ReviewData:
    """
    Standardized internal data structure for a single review.
    Used to bridge the API response and the Database model.
    """
    review_id: str
    author_name: str
    rating: float
    text: str
    time_created: datetime
    sentiment: Optional[str] = None  # positive/neutral/negative
    review_title: Optional[str] = None
    helpful_votes: Optional[int] = 0
    source_platform: Optional[str] = None  # e.g., Google, Yelp
    competitor_name: Optional[str] = None
    additional_fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompanyReviews:
    """
    Container for a batch of reviews belonging to a company.
    """
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


# ──────────────────────────────────────────────────────────────────────────────
# Service Layer (The Logic Engine)
# ──────────────────────────────────────────────────────────────────────────────

class OutscraperReviewsService:
    """
    Primary service for interacting with the Outscraper API Client.
    Handles the transformation of raw API JSON into ReviewData objects.
    """
    PAGE_SIZE = 100

    def __init__(self, api_client: Any):
        self.client = api_client

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime:
        """Ensures that timestamps from various sources are converted to naive datetime."""
        if not value:
            return datetime.now()
        if isinstance(value, (int, float)):
            try: return datetime.fromtimestamp(float(value))
            except: pass
        if isinstance(value, str):
            try:
                # Handle ISO format and strip timezones for PostgreSQL compatibility
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt.replace(tzinfo=None)
            except:
                try: return datetime.strptime(value, "%Y-%m-%d")
                except: pass
        return datetime.now()

    def _to_review_data(self, row: Dict[str, Any], competitor_name: Optional[str] = None) -> Optional[ReviewData]:
        """Maps a raw Outscraper JSON row to a ReviewData object."""
        # Drill down into Outscraper-specific fields
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
        """
        Fetches and maps reviews for a single place_id.
        CRITICAL: Uses 'await' to ensure the async client completes.
        """
        # Call the OutscraperClient defined in main.py
        response = await self.client.get_reviews(place_id=place_id, limit=limit)
        
        # Outscraper responses are often wrapped in a list; main.py handles the list,
        # but we safeguard here as well.
        raw_list = response.get("reviews", [])
        
        if not raw_list:
            logger.warning(f"⚠️ No reviews returned from API for Place ID: {place_id}")
            return []

        logger.info(f"✅ Mapping {len(raw_list)} reviews for {competitor_name or 'Primary Company'}")
        return [self._to_review_data(r, competitor_name) for r in raw_list if r]


# ──────────────────────────────────────────────────────────────────────────────
# Persistence Layer (The Database Engine)
# ──────────────────────────────────────────────────────────────────────────────



async def run_batch_review_ingestion(api_client: Any, primary_company_id: int, entities: List[Dict[str, Any] | str]):
    """
    Main function used by the Dashboard Sync button and the Daily Scheduler.
    Saves data for the primary company and all provided competitors.
    """
    logger.info(f"🚀 Batch Ingestion Triggered for Company ID: {primary_company_id}")
    service = OutscraperReviewsService(api_client)
    
    # 1. Standardize entities into a list of dictionaries
    processed_entities = []
    for ent in entities:
        if isinstance(ent, str):
            processed_entities.append({"place_id": ent, "name": None})
        else:
            processed_entities.append({
                "place_id": ent.get("place_id"),
                "name": ent.get("name") or ent.get("competitor_name")
            })

    # 2. Process each entity and persist to the database
    async with get_session() as session:
        total_new_reviews = 0
        
        for ent in processed_entities:
            pid = ent['place_id']
            c_name = ent['name']
            
            # Fetch reviews from API
            fetched_reviews = await service.fetch_entity_reviews(
                place_id=pid, 
                limit=500, 
                competitor_name=c_name
            )
            
            # Save to Database
            for rd in fetched_reviews:
                if not rd: continue
                
                # Duplicate Guard: Check if review already exists for this company
                stmt = select(Review).where(and_(
                    Review.company_id == primary_company_id,
                    Review.google_review_id == rd.review_id
                ))
                existing = await session.execute(stmt)
                if existing.scalar_one_or_none():
                    continue

                # Create the database model instance
                db_review = Review(
                    company_id=primary_company_id,
                    google_review_id=rd.review_id,
                    author_name=rd.author_name,
                    rating=rd.rating,
                    text=rd.text,
                    google_review_time=rd.time_created,
                    competitor_name=rd.competitor_name,  # Critical for competitor charts
                    source_platform=rd.source_platform
                )
                session.add(db_review)
                total_new_reviews += 1
        
        # 3. Final Commit
        if total_new_reviews > 0:
            await session.commit()
            logger.info(f"✨ Successfully committed {total_new_reviews} new reviews to PostgreSQL.")
        else:
            logger.info("ℹ️ Sync complete. No new reviews were found.")

# ──────────────────────────────────────────────────────────────────────────────
# Helper Functions for Public Callers
# ──────────────────────────────────────────────────────────────────────────────

async def ingest_multi_company_reviews(primary_company_id: int, entities: List[Dict[str, Any] | str], api_client: Any) -> int:
    """Wrapper to run the ingestion and return the total count saved."""
    # This matches the pattern called by your dashboard router
    return await run_batch_review_ingestion(api_client, primary_company_id, entities)
