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
    Bypasses the official Google 5-review limit.
    """
    def __init__(self):
        # Explicitly uses the OUTSCAPTER_KEY defined in config.py
        self.api_key = settings.OUTSCAPTER_KEY
        # Outscraper Google Maps Reviews V2 Endpoint
        self.base_url = "https://api.app.outscraper.com/maps/reviews-v2"

    async def fetch_reviews(self, query: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Fetches up to `limit` reviews for a given business (Place ID or Name).
        """
        headers = {"X-API-KEY": self.api_key}
        params = {
            "query": query,
            "reviewsLimit": limit,  # Outscraper V2 uses reviewsLimit
            "async": "false",
            "sort": "newest",
            "ignoreEmpty": "true"
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            try:
                logger.info(f"Triggering Outscraper Sync: query={query} limit={limit}")
                response = await client.get(self.base_url, headers=headers, params=params)
                
                if response.status_code != 200:
                    logger.error(f"Outscraper API Error {response.status_code}: {response.text}")
                    return []

                data = response.json()
                results = data.get("data", [])
                all_reviews = []

                # Outscraper returns a list of result objects (one per query)
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
                            "likes": rev.get("review_likes") or rev.get("likes"),
                            "response_text": rev.get("owner_answer") or rev.get("response_text"),
                            "response_datetime": rev.get("owner_answer_timestamp_datetime_utc"),
                            "language": rev.get("review_language") or rev.get("language"),
                            "place_id": result.get("place_id") or query
                        })

                logger.info(f"Outscraper found {len(all_reviews)} reviews for {query}")
                return all_reviews
            except Exception as e:
                logger.error(f"Critical failure in Outscraper fetch: {e}")
                return []

# Instantiate the service
outscraper_service = OutscraperReviewsService()

async def ingest_company_reviews(place_id: str, company_id: int):
    """
    Main ingestion logic. Pulls data from Outscraper and saves unique records to Postgres.
    """
    # Fetch 1000 reviews to ensure a complete dataset
    reviews_data = await outscraper_service.fetch_reviews(place_id, limit=1000)
    
    async with get_session() as session:
        new_count = 0
        for rd in reviews_data:
            # Prevent Duplicates via Google's unique Review ID
            exists = await session.execute(
                select(Review).where(Review.google_review_id == rd["reviewId"])
            )
            if exists.scalar_one_or_none():
                continue

            # Parse review date safely
            review_date = datetime.utcnow()
            if rd["time_str"]:
                try:
                    review_date = datetime.fromisoformat(rd["time_str"].replace("Z", "+00:00"))
                except:
                    pass

            # Parse owner response date
            response_date = None
            if rd.get("response_datetime"):
                try:
                    response_date = datetime.fromisoformat(rd.get("response_datetime").replace("Z", "+00:00"))
                except:
                    pass

            # Create the Review object aligned with your Model.py
            review = Review(
                company_id=company_id,
                google_review_id=rd["reviewId"],
                author_name=rd["author"],
                author_url=rd.get("author_url"),
                profile_photo_url=rd.get("author_image"),
                rating=rd["rating"],
                text=rd["text"],
                google_review_time=review_date,
                review_reply_text=rd.get("response_text")
            )
            session.add(review)
            new_count += 1
        
        await session.commit()
        logger.info(f"Ingestion complete: Added {new_count} new reviews for company {company_id}.")

async def fetch_competitor_reviews(competitor_name: str, limit: int = 500):
    """Fetch reviews for a competitor business."""
    return await outscraper_service.fetch_reviews(query=competitor_name, limit=limit)

async def fetch_place_details(place_id: str):
    """Placeholder to maintain compatibility with existing route imports."""
    return {"name": "Business Location"}
