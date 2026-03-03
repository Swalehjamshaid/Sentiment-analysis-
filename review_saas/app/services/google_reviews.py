# filename: app/services/google_reviews.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import googlemaps  # type: ignore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.models import Company, Review
from app.services.sentiment import score as get_sentiment_score, label as get_sentiment_label
from app.core.config import settings

class GoogleReviewsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        # Use centralized settings for the API key
        api_key = settings.GOOGLE_PLACES_API_KEY or settings.GOOGLE_MAPS_API_KEY
        if not api_key:
            raise RuntimeError("GOOGLE_PLACES_API_KEY or GOOGLE_MAPS_API_KEY not set")
        self.gmaps = googlemaps.Client(key=api_key)

    async def fetch_place_reviews(self, place_id: str) -> List[Dict[str, Any]]:
        """Fetch and process reviews with sentiment analysis."""
        place_details = self.gmaps.place(
            place_id=place_id, 
            fields=["name", "rating", "reviews", "user_ratings_total"]
        )
        
        reviews = place_details.get("result", {}).get("reviews", [])
        processed_reviews = []

        for r in reviews:
            text_content = r.get("text") or ""
            s_score = get_sentiment_score(text_content)
            s_label = get_sentiment_label(s_score)

            processed_reviews.append({
                "source_id": f"place_{r.get('author_name')}_{r.get('time')}",  
                "author_name": r.get("author_name"),
                "rating": int(r.get("rating", 0)),
                "text": text_content,
                "review_time": datetime.fromtimestamp(r.get("time"), tz=timezone.utc),
                "sentiment_score": s_score,
                "sentiment_label": s_label,
            })
        return processed_reviews

    async def save_reviews_to_db(self, company: Company, reviews: List[Dict[str, Any]]) -> int:
        """Saves reviews and returns the count of new items added."""
        ingested = 0
        for r in reviews:
            stmt = select(Review.id).where(
                Review.company_id == company.id, 
                Review.source_id == r["source_id"]
            )
            existing = (await self.db.execute(stmt)).scalar_one_or_none()
            
            if existing:
                continue

            db_review = Review(
                company_id=company.id,
                source_id=r["source_id"],
                author_name=r.get("author_name"),
                rating=r.get("rating"),
                text=r.get("text"),
                review_time=r.get("review_time"),
                sentiment_score=r.get("sentiment_score"),
                sentiment_label=r.get("sentiment_label")
            )
            self.db.add(db_review)
            ingested += 1

        company.last_updated = datetime.now(tz=timezone.utc)
        await self.db.commit()
        return ingested

# ──────────────────────────────────────────────────────────────
# BRIDGE FUNCTIONS (To fix ImportErrors in routes)
# ──────────────────────────────────────────────────────────────

async def ingest_company_reviews(session: AsyncSession, company: Company) -> dict:
    """Fixes ImportError in app/routes/companies.py and dashboard.py"""
    service = GoogleReviewsService(session)
    reviews = await service.fetch_place_reviews(company.place_id)
    count = await service.save_reviews_to_db(company, reviews)
    return {"ingested": count}

async def fetch_place_details(place_id: str) -> dict:
    """Fixes ImportError in app/routes/reviews.py"""
    # Create a temporary client for simple metadata fetching
    api_key = settings.GOOGLE_PLACES_API_KEY or settings.GOOGLE_MAPS_API_KEY
    gmaps = googlemaps.Client(key=api_key)
    return gmaps.place(
        place_id=place_id, 
        fields=["name", "rating", "reviews", "user_ratings_total"]
    )
