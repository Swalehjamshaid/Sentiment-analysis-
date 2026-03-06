# File: app/routes/reviews.py

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

router = APIRouter(
    prefix="/reviews",
    tags=["Reviews"]
)

class GoogleReviewsService:

    def __init__(self):
        self.api_key = settings.OUTSCAPTER_KEY
        self.base_url = "https://api.outscraper.com/maps/reviews-v3"

    async def fetch_reviews(self, query: str, limit: int = 200):

        headers = {
            "X-API-KEY": self.api_key
        }

        params = {
            "query": query,
            "reviewsLimit": limit,   # IMPORTANT PARAMETER
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
                    logger.error(f"Outscraper API Error: {response.text}")
                    return []

                data = response.json()

                results = data.get("data", [])

                mapped_reviews = []

                for result in results:

                    reviews = result.get("reviews_data", [])

                    for rev in reviews:

                        mapped_reviews.append({
                            "reviewId": rev.get("review_id"),
                            "author": rev.get("author_title"),
                            "rating": rev.get("review_rating"),
                            "text": rev.get("review_text"),
                            "time_str": rev.get("review_datetime_utc"),
                            "photo": rev.get("author_image")
                        })

                return mapped_reviews

            except Exception as e:
                logger.error(f"Outscraper fetch failed: {e}")
                return []


google_reviews_service = GoogleReviewsService()


@router.get("/fetch")
async def fetch_reviews(query: str, limit: int = 200):

    reviews = await google_reviews_service.fetch_reviews(query, limit)

    if not reviews:
        raise HTTPException(status_code=404, detail="No reviews found")

    return {
        "total_reviews": len(reviews),
        "reviews": reviews
    }
