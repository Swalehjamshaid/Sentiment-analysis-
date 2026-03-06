# File: review_saas/app/services/google_reviews.py

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
    Service to fetch Google Maps reviews and competitor reviews via Outscraper API.
    """
    def __init__(self):
        self.api_key = settings.OUTSCAPTER_KEY
        self.base_url = "https://api.outscraper.com/v2/google-maps/reviews"

    async def fetch_reviews(self, query: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Fetches up to `limit` reviews for a given business or competitor.
        """
        headers = {"X-API-KEY": self.api_key}
        params = {
            "query": query,
            "limit": limit,  # fetch all reviews in one request
            "async": False,
            "sort": "newest"
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            try:
                logger.info(f"Fetching reviews for query={query} limit={limit}")
                response = await client.get(self.base_url, headers=headers, params=params)
                if response.status_code != 200:
                    logger.error(f"Outscraper API Error {response.status_code}: {response.text}")
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

                logger.info(f"Fetched {len(all_reviews)} reviews for query={query}")
                return all_reviews
            except Exception as e:
                logger.error(f"Failed to fetch reviews from Outscraper: {e}")
                return []

# Instantiate the service
outscraper_service = OutscraperReviewsService()


async def ingest_company_reviews(place_id: str, company_id: int):
    """
    Fetches reviews and saves unique entries to Postgres.
    """
    reviews_data = await outscraper_service.fetch_reviews(place_id, limit=1000)
    
    async with get_session() as session:
        new_count = 0
        for rd in reviews_data:
            exists = await session.execute(
                select(Review).where(Review.google_review_id == rd["reviewId"])
            )
            if exists.scalar_one_or_none():
                continue

            # parse review date
            review_date = datetime.utcnow()
            if rd["time_str"]:
                try:
                    review_date = datetime.fromisoformat(rd["time_str"].replace("Z", "+00:00"))
                except Exception:
                    pass

            # parse owner response date
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
        logger.info(f"Ingested {new_count} new reviews for company {company_id}.")


async def fetch_competitor_reviews(competitor_name: str, limit: int = 500):
    """
    Fetch reviews for a competitor business.
    """
    return await outscraper_service.fetch_reviews(query=competitor_name, limit=limit)


async def fetch_place_details(place_id: str):
    """
    Placeholder function for UI compatibility.
    """
    return {"name": "Business Location"}
