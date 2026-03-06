# ============================================
# File: app/routes/reviews.py
# ============================================

from fastapi import APIRouter, HTTPException
import httpx
import logging
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy import select

from app.core.config import settings
from app.core.db import get_session
from app.core.models import Review

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# FastAPI Router (REQUIRED or server will crash)
# ---------------------------------------------------------
router = APIRouter(
    prefix="/reviews",
    tags=["Reviews"]
)

# ---------------------------------------------------------
# Google Reviews Service (Outscraper)
# ---------------------------------------------------------
class GoogleReviewsService:

    def __init__(self):
        self.api_key = settings.OUTSCAPTER_KEY
        self.base_url = "https://api.outscraper.com/v2/google-maps/reviews"

    async def fetch_reviews(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch reviews from Outscraper
        (bypasses Google 5-review API limitation)
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

                response = await client.get(
                    self.base_url,
                    headers=headers,
                    params=params
                )

                if response.status_code != 200:
                    logger.error(
                        f"Outscraper API Error: {response.status_code} - {response.text}"
                    )
                    return []

                data = response.json()

                results = data.get("data", [])

                mapped_reviews = []

                for result in results:

                    reviews = result.get("reviews_data", [])

                    for rev in reviews:

                        mapped_reviews.append({
                            "reviewId": rev.get("review_id"),
                            "author": rev.get("author_title", "Anonymous"),
                            "rating": rev.get("review_rating") or rev.get("rating"),
                            "text": rev.get("review_text", ""),
                            "time_str": rev.get("review_datetime_utc"),
                            "photo": rev.get("author_image")
                        })

                return mapped_reviews

            except Exception as e:
                logger.error(f"Outscraper request failed: {e}")
                return []


# Singleton instance
google_reviews_service = GoogleReviewsService()


# ---------------------------------------------------------
# API Route - Fetch Reviews (Testing Endpoint)
# ---------------------------------------------------------
@router.get("/fetch")
async def fetch_reviews(query: str, limit: int = 50):
    """
    Fetch reviews directly from Outscraper
    """

    reviews = await google_reviews_service.fetch_reviews(query, limit)

    if not reviews:
        raise HTTPException(status_code=404, detail="No reviews found")

    return {
        "total_reviews": len(reviews),
        "reviews": reviews
    }


# ---------------------------------------------------------
# Ingest Reviews Into Database
# ---------------------------------------------------------
async def ingest_company_reviews(place_id: str, company_id: int):

    reviews_data = await google_reviews_service.fetch_reviews(place_id, limit=100)

    async with get_session() as session:

        new_count = 0

        for rd in reviews_data:

            exists = await session.execute(
                select(Review).where(
                    Review.google_review_id == rd["reviewId"]
                )
            )

            if exists.scalar_one_or_none():
                continue

            review_date = datetime.utcnow()

            if rd["time_str"]:
                try:
                    review_date = datetime.fromisoformat(
                        rd["time_str"].replace("Z", "")
                    )
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

        logger.info(f"Ingested {new_count} reviews for company {company_id}")


# ---------------------------------------------------------
# Dummy place details function (compatibility)
# ---------------------------------------------------------
async def fetch_place_details(place_id: str):

    return {
        "name": "Business Location"
    }
