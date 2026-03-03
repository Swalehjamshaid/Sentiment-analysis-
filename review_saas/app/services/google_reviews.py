# filename: app/services/google_reviews.py
from __future__ import annotations
from typing import Any, Dict, List
from datetime import datetime, timezone
import hashlib
import os
import googlemaps  # type: ignore
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.models import Company, Review
from app.services.sentiment import score  # returns sentiment score (-1 to 1) and label

# Load API keys from environment
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
GOOGLE_BUSINESS_API_KEY = os.getenv("GOOGLE_BUSINESS_API_KEY")

# Initialize Google Maps client (for Places API)
gmaps_client = googlemaps.Client(key=GOOGLE_PLACES_API_KEY or GOOGLE_MAPS_API_KEY)


class GoogleReviewsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch_place_reviews(self, place_id: str) -> List[Dict[str, Any]]:
        """Fetch public reviews from Google Places API"""
        place_details = gmaps_client.place(place_id=place_id, fields=["name", "rating", "reviews"])
        reviews = place_details.get("result", {}).get("reviews", [])
        processed_reviews = []

        for r in reviews:
            sentiment_score, sentiment_label = score(r.get("text", ""))
            processed_reviews.append({
                "source_id": f"place_{r.get('author_name')}_{r.get('time')}",  # unique per review
                "author_name": r.get("author_name"),
                "rating": int(r.get("rating", 0)),
                "text": r.get("text"),
                "review_time": datetime.fromtimestamp(r.get("time"), tz=timezone.utc),
                "sentiment_score": sentiment_score,
                "sentiment_label": sentiment_label,
                "keywords": [],  # optional: implement keyword extraction
            })
        return processed_reviews

    async def fetch_business_reviews(self, account_id: str) -> List[Dict[str, Any]]:
        """Fetch reviews from your own Google Business account"""
        if not GOOGLE_BUSINESS_API_KEY:
            raise ValueError("GOOGLE_BUSINESS_API_KEY not set in environment")

        url = f"https://mybusiness.googleapis.com/v4/accounts/{account_id}/locations/reviews"
        headers = {"Authorization": f"Bearer {GOOGLE_BUSINESS_API_KEY}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

        processed_reviews = []
        for r in data.get("reviews", []):
            sentiment_score, sentiment_label = score(r.get("comment", ""))
            processed_reviews.append({
                "source_id": r.get("reviewId"),
                "author_name": r.get("reviewer", {}).get("displayName"),
                "rating": int(r.get("starRating", 0)),
                "text": r.get("comment"),
                "review_time": datetime.fromisoformat(r.get("createTime").replace("Z", "+00:00")),
                "sentiment_score": sentiment_score,
                "sentiment_label": sentiment_label,
                "keywords": [],  # optional
            })
        return processed_reviews

    async def save_reviews_to_db(self, company: Company, reviews: List[Dict[str, Any]]):
        """Save reviews into database with UniqueConstraint on (company_id, source_id)"""
        for r in reviews:
            existing = await self.db.scalar(
                Review.__table__.select().where(
                    (Review.company_id == company.id) &
                    (Review.source_id == r["source_id"])
                )
            )
            if existing:
                continue  # skip duplicate

            db_review = Review(
                company_id=company.id,
                source_id=r["source_id"],
                author_name=r.get("author_name"),
                rating=r.get("rating"),
                text=r.get("text"),
                review_time=r.get("review_time"),
                sentiment_score=r.get("sentiment_score"),
                sentiment_label=r.get("sentiment_label"),
                keywords=r.get("keywords") or [],
            )
            self.db.add(db_review)
        await self.db.commit()
