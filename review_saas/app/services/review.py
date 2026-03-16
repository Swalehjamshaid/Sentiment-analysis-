# filename: app/services/review.py

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.models import Review 

logger = logging.getLogger(__name__)

class OutscraperReviewsClient:
    def __init__(self, *, base_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.OUTSCRAPER_BASE_URL).rstrip("/")
        self.api_key = (api_key or settings.OUTSCRAPER_API_KEY).strip()
        self.reviews_endpoint = f"{self.base_url}/maps/reviews-v3"

    async def fetch_reviews(self, company_obj: Any, max_reviews: int = 10000) -> List[Dict[str, Any]]:
        query = getattr(company_obj, "google_place_id", None) or getattr(company_obj, "name", None)
        
        # We use reviewsLimit for the count-based approach
        params = {
            "query": query, 
            "reviewsLimit": max_reviews, 
            "async": "false"
        }
        headers = {"X-API-KEY": self.api_key}

        # Increased timeout for large data sets
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, read=300.0)) as client:
            response = await client.get(self.reviews_endpoint, params=params, headers=headers)
            response.raise_for_status()
            full_response = response.json()
            
            results_list = full_response.get("data", [])
            
            if isinstance(results_list, list) and len(results_list) > 0:
                return results_list[0].get("reviews_data", [])
            
            logger.warning(f"No reviews found or unexpected structure for {query}")
            return []

async def ingest_outscraper_reviews(company_obj: Any, session: AsyncSession, max_reviews: int = 10000) -> int:
    client = OutscraperReviewsClient()
    raw_reviews = await client.fetch_reviews(company_obj, max_reviews=max_reviews)
    
    new_count = 0
    for raw in raw_reviews:
        ext_id = raw.get("review_id")
        if not ext_id:
            continue
            
        stmt = select(Review).where(
            (Review.company_id == company_obj.id) & 
            (Review.google_review_id == ext_id)
        )
        existing = await session.execute(stmt)
        
        if existing.scalars().first():
            continue

        raw_ts = raw.get("review_datetime_utc")
        dt_obj = None
        if raw_ts:
            try:
                dt_obj = datetime.strptime(raw_ts, "%m/%d/%Y %H:%M:%S")
            except (ValueError, TypeError):
                try:
                    dt_obj = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse timestamp: {raw_ts}")

        new_review = Review(
            company_id=company_obj.id,
            google_review_id=ext_id,
            author_name=raw.get("author_title"),
            rating=raw.get("review_rating"),
            text=raw.get("review_text"), 
            google_review_time=dt_obj,
            review_url=raw.get("review_link"),
            source_platform="Google"
        )
        session.add(new_review)
        new_count += 1

    if new_count > 0:
        await session.commit() 
    return new_count
