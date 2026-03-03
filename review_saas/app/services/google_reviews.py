# filename: app/services/google_reviews.py
from __future__ import annotations
from typing import Any, Dict, List
from datetime import datetime, timezone
import googlemaps
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.models import Company, Review
from app.services.sentiment import score as get_sentiment_score, label as get_sentiment_label
from app.core.config import settings

class GoogleReviewsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        api_key = settings.GOOGLE_PLACES_API_KEY or settings.GOOGLE_MAPS_API_KEY
        self.gmaps = googlemaps.Client(key=api_key)

    async def fetch_place_reviews(self, place_id: str) -> List[Dict[str, Any]]:
        # Fetching specific fields to save quota and ensure data exists
        place_details = self.gmaps.place(place_id=place_id, fields=["reviews"])
        reviews = place_details.get("result", {}).get("reviews", [])
        processed = []
        for r in reviews:
            text = r.get("text") or ""
            score = get_sentiment_score(text)
            processed.append({
                "source_id": f"place_{r.get('author_name')}_{r.get('time')}",
                "author_name": r.get("author_name"),
                "rating": int(r.get("rating", 0)),
                "text": text,
                "review_time": datetime.fromtimestamp(r.get("time"), tz=timezone.utc),
                "sentiment_score": score,
                "sentiment_label": get_sentiment_label(score)
            })
        return processed

    async def save_reviews_to_db(self, company: Company, reviews: List[Dict[str, Any]]) -> int:
        count = 0
        for r in reviews:
            # Prevent duplicate entries
            stmt = select(Review.id).where(Review.company_id == company.id, Review.source_id == r["source_id"])
            if (await self.db.execute(stmt)).scalar_one_or_none(): 
                continue
            
            self.db.add(Review(
                company_id=company.id, source_id=r["source_id"], author_name=r["author_name"],
                rating=r["rating"], text=r["text"], review_time=r["review_time"],
                sentiment_score=r["sentiment_score"], sentiment_label=r["sentiment_label"]
            ))
            count += 1
        await self.db.commit()
        return count

# CRITICAL BRIDGE: This fixes the ImportError in your routes
async def ingest_company_reviews(session: AsyncSession, company: Company) -> dict:
    service = GoogleReviewsService(session)
    reviews = await service.fetch_place_reviews(company.place_id)
    count = await service.save_reviews_to_db(company, reviews)
    return {"ingested": count}
