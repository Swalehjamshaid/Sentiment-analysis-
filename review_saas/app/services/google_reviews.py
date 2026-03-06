# File: review_saas/app/services/google_reviews.py
import httpx
import logging
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.core.db import get_session
from app.core.models import Review
from sqlalchemy import select

logger = logging.getLogger(__name__)

class GoogleReviewsService:
    def __init__(self):
        # Matches the key name in your Railway Variables screenshot
        self.api_key = settings.OUTSCAPTER_API_KEY 
        self.base_url = "https://api.outscapter.com/v1/reviews/google-maps"

    async def fetch_reviews(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetches up to 'limit' reviews from Outscraper for a specific Place ID or URL.
        """
        all_reviews = []
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        # Outscraper expects 'queries' as a list
        payload = {
            "queries": [query],
            "limit": limit,
            "sort": "newest"
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(self.base_url, headers=headers, json=payload)
                if response.status_code != 200:
                    logger.error(f"Outscraper Error: {response.status_code} - {response.text}")
                    return []

                data = response.json()
                results = data.get("data", [])
                
                for result in results:
                    # Outscraper uses 'reviews_data' for the list of reviews
                    reviews = result.get("reviews_data", [])
                    for rev in reviews:
                        all_reviews.append({
                            "reviewId": rev.get("review_id"),
                            "author": rev.get("author_title"),
                            "rating": rev.get("rating"),
                            "text": rev.get("review_text"),
                            "time": rev.get("review_datetime_utc"),
                            "photo": rev.get("author_image")
                        })
                
                logger.info(f"Outscraper returned {len(all_reviews)} reviews.")
                return all_reviews
            except Exception as e:
                logger.error(f"Request to Outscraper failed: {str(e)}")
                return []

google_reviews_service = GoogleReviewsService()

async def ingest_company_reviews(place_id: str, company_id: int):
    """
    Orchestrates fetching from Outscraper and saving to Postgres.
    """
    reviews_data = await google_reviews_service.fetch_reviews(place_id, limit=100)
    
    async with get_session() as session:
        new_count = 0
        for rd in reviews_data:
            # Prevent duplicates by checking the unique Google Review ID
            existing = await session.execute(
                select(Review).where(Review.google_review_id == rd["reviewId"])
            )
            if existing.scalar_one_or_none():
                continue

            review = Review(
                company_id=company_id,
                google_review_id=rd["reviewId"],
                author_name=rd["author"],
                rating=rd["rating"],
                text=rd["text"],
                profile_photo_url=rd["photo"]
                # Note: Ensure rd["time"] is parsed to a datetime object if your model requires it
            )
            session.add(review)
            new_count += 1
        
        await session.commit()
        logger.info(f"Saved {new_count} new reviews to the database.")

async def fetch_place_details(place_id: str):
    # Simplified detail fetch using Outscraper Search
    return {"name": "Business Location"} # Placeholder or implement Outscraper search
