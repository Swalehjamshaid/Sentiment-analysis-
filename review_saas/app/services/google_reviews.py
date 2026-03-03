# filename: app/services/google_reviews.py
from __future__ import annotations
from datetime import datetime, timezone
import googlemaps
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.models import Company, Review
from app.core.config import settings
from app.services.sentiment import score as get_sentiment_score, label as get_sentiment_label

class GoogleReviewsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        api_key = settings.GOOGLE_PLACES_API_KEY or settings.GOOGLE_MAPS_API_KEY
        self.gmaps = googlemaps.Client(key=api_key)

    async def ingest_reviews(self, company_id: int, place_id: str):
        # Fetching place details and the 5 most recent reviews (Google default)
        details = self.gmaps.place(place_id=place_id, fields=["rating", "reviews", "user_ratings_total"])
        result = details.get("result", {})
        reviews = result.get("reviews", [])

        for r in reviews:
            source_id = str(r.get('time'))
            # Deduplication check
            stmt = select(Review.id).where(Review.company_id == company_id, Review.source_id == source_id)
            if (await self.db.execute(stmt)).scalar_one_or_none():
                continue

            # Process Sentiment
            text_content = r.get("text") or ""
            s_score = get_sentiment_score(text_content)
            
            new_review = Review(
                company_id=company_id,
                source_id=source_id,
                author_name=r.get("author_name"),
                rating=r.get("rating"),
                text=text_content,
                # Fix for the date crash: Ensure it is a UTC aware datetime object
                review_time=datetime.fromtimestamp(r.get("time"), tz=timezone.utc),
                sentiment_score=s_score,
                sentiment_label=get_sentiment_label(s_score)
            )
            self.db.add(new_review)

        # Sync metadata back to Company table
        await self.db.execute(
            update(Company).where(Company.id == company_id).values(
                avg_rating=result.get("rating", 0.0),
                review_count=result.get("user_ratings_total", 0),
                last_updated=datetime.now(tz=timezone.utc)
            )
        )
        await self.db.commit()

# --- THE CRITICAL EXPORTED FUNCTION ---
async def ingest_company_reviews(session: AsyncSession, company_id: int, place_id: str):
    """Bridge function that fixes the ImportError in companies.py"""
    service = GoogleReviewsService(session)
    await service.ingest_reviews(company_id, place_id)
