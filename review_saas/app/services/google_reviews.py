import httpx
import logging
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy import select
from app.core.config import settings
from app.core.db import get_session
from app.core.models import Review

logger = logging.getLogger(__name__)

class GoogleReviewsService:
    def __init__(self):
        # Matches the variable name in config.py
        self.api_key = settings.OUTSCAPTER_KEY 
        # Endpoint for Google Maps Reviews
        self.base_url = "https://api.outscraper.com/v2/google-maps/reviews"

    async def fetch_reviews(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetches up to 100 reviews from Outscraper.
        This bypasses the standard 5-review limit.
        """
        headers = {"X-API-KEY": self.api_key}
        params = {
            "query": query,
            "limit": limit,
            "async": "false",
            "sort": "newest"
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.get(self.base_url, headers=headers, params=params)
                
                if response.status_code != 200:
                    logger.error(f"Outscraper Error: {response.status_code} - {response.text}")
                    return []

                data = response.json()
                results = data.get("data", [])
                
                all_mapped = []
                for result in results:
                    # Outscraper nests reviews inside 'reviews_data'
                    reviews = result.get("reviews_data", [])
                    for rev in reviews:
                        all_mapped.append({
                            "reviewId": rev.get("review_id"),
                            "author": rev.get("author_title", "Anonymous"),
                            "rating": rev.get("review_rating") or rev.get("rating"),
                            "text": rev.get("review_text", ""),
                            "time_str": rev.get("review_datetime_utc"),
                            "photo": rev.get("author_image")
                        })
                return all_mapped
            except Exception as e:
                logger.error(f"Failed to fetch from Outscraper: {e}")
                return []

google_reviews_service = GoogleReviewsService()

async def ingest_company_reviews(place_id: str, company_id: int):
    """
    Fetches data from Outscraper and saves unique records to Postgres.
    """
    # Requesting 100 reviews to ensure we get a full dataset
    reviews_data = await google_reviews_service.fetch_reviews(place_id, limit=100)
    
    async with get_session() as session:
        new_count = 0
        for rd in reviews_data:
            # Check for existing review to prevent duplicates
            exists = await session.execute(
                select(Review).where(Review.google_review_id == rd["reviewId"])
            )
            if exists.scalar_one_or_none():
                continue

            # Parse datetime
            review_date = datetime.utcnow()
            if rd["time_str"]:
                try:
                    review_date = datetime.fromisoformat(rd["time_str"].replace("Z", ""))
                except:
                    pass

            review = Review(
                company_id=company_id,
                google_review_id=rd["reviewId"],
                author_name=rd["author"],
                rating=rd["rating"],
                text=rd["text"],
                profile_photo_url=rd["photo"],
                google_review_time=review_date
            )
            session.add(review)
            new_count += 1
        
        await session.commit()
        logger.info(f"Ingested {new_count} reviews for company {company_id}.")

async def fetch_place_details(place_id: str):
    """Placeholder for UI compatibility."""
    return {"name": "Business Location"}
