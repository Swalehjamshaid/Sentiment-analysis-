# filename: review_saas/app/services/google_reviews.py

import httpx
import logging
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy import select
from app.core.config import settings
from app.core.db import get_session
from app.core.models import Review

logger = logging.getLogger(__name__)

class OutscraperReviewsService:
    """
    Service to fetch Google Maps reviews via Outscraper API.
    """
    def __init__(self):
        # Use the key from .env / config.py
        self.api_key = settings.OUTSCAPTER_KEY  # match your .env key
        self.base_url = "https://api.outscraper.com/v2/google-maps/reviews"

    async def fetch_reviews(self, query: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Fetches up to `limit` reviews from Outscraper for a business.
        """
        headers = {"X-API-KEY": self.api_key}
        params = {
            "query": query,
            "limit": limit,
            "async": False,
            "sort": "newest"
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            try:
                logger.info(f"Fetching {limit} reviews for place_id={query}")
                response = await client.get(self.base_url, headers=headers, params=params)
                
                if response.status_code != 200:
                    logger.error(f"Outscraper Error: {response.status_code} - {response.text}")
                    return []

                data = response.json()
                results = data.get("data", [])
                
                all_reviews = []
                for result in results:
                    reviews = result.get("reviews_data", [])
                    for rev in reviews:
                        all_reviews.append({
                            "reviewId": rev.get("review_id"),
                            "author": rev.get("author_title") or "Anonymous",
                            "author_url": rev.get("author_url"),
                            "author_image": rev.get("author_image"),
                            "rating": rev.get("review_rating") or rev.get("rating") or 0,
                            "text": rev.get("review_text") or "",
                            "time_str": rev.get("review_datetime_utc"),
                            "likes": rev.get("likes"),
                            "response_text": rev.get("response_text"),
                            "response_datetime": rev.get("response_datetime_utc"),
                            "language": rev.get("language"),
                            "place_id": rev.get("place_id")
                        })
                logger.info(f"Fetched {len(all_reviews)} reviews for place_id={query}")
                return all_reviews
            except Exception as e:
                logger.error(f"Failed to fetch from Outscraper: {e}")
                return []

# Instantiate the service
outscraper_service = OutscraperReviewsService()

async def ingest_company_reviews(place_id: str, company_id: int):
    """
    Fetch reviews from Outscraper and save unique entries to Postgres.
    """
    reviews_data = await outscraper_service.fetch_reviews(place_id, limit=1000)
    
    async with get_session() as session:
        new_count = 0
        for rd in reviews_data:
            # Avoid duplicates
            exists = await session.execute(
                select(Review).where(Review.google_review_id == rd["reviewId"])
            )
            if exists.scalar_one_or_none():
                continue

            # Parse review datetime
            review_date = datetime.utcnow()
            if rd["time_str"]:
                try:
                    review_date = datetime.fromisoformat(rd["time_str"].replace("Z", "+00:00"))
                except Exception:
                    pass

            # Parse owner response datetime
            response_date = None
            if rd.get("response_datetime"):
                try:
                    response_date = datetime.fromisoformat(rd.get("response_datetime").replace("Z", "+00:00"))
                except Exception:
                    pass

            review = Review(
                company_id=company_id,
                google_review_id=rd["reviewId"],
                author_name=rd["author"],
                author_url=rd.get("author_url"),
                profile_photo_url=rd.get("author_image"),
                rating=rd["rating"],
                text=rd["text"],
                review_likes=rd.get("likes"),
                owner_response=rd.get("response_text"),
                owner_response_time=response_date,
                review_language=rd.get("language"),
                google_review_time=review_date,
                place_id=rd.get("place_id")
            )
            session.add(review)
            new_count += 1
        
        await session.commit()
        logger.info(f"Ingested {new_count} reviews for company {company_id}.")

async def fetch_place_details(place_id: str):
    """
    Placeholder function for UI compatibility.
    """
    return {"name": "Business Location"}
