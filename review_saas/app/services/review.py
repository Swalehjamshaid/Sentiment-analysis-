# filename: app/services/review.py

from __future__ import annotations
import logging
import asyncio
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

    async def fetch_reviews(self, company_obj: Any, limit: int = 500, skip: int = 0) -> List[Dict[str, Any]]:
        """
        Fetches a specific batch (bag) of reviews using 'reviewsLimit' and 'skip'.
        Using small batches (500) prevents timeouts and allows sequential progress.
        """
        query = getattr(company_obj, "google_place_id", None) or getattr(company_obj, "name", None)
        
        params = {
            "query": query, 
            "reviewsLimit": limit, 
            "skip": skip,  # The offset to get the next 'bag'
            "async": "false",
            "ignoreEmpty": "true"
        }
        headers = {"X-API-KEY": self.api_key}

        # Increased timeout to handle large data processing on the API side
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=300.0)) as client:
            try:
                response = await client.get(self.reviews_endpoint, params=params, headers=headers)
                response.raise_for_status()
                full_response = response.json()
                
                results_list = full_response.get("data", [])
                
                if isinstance(results_list, list) and len(results_list) > 0:
                    return results_list[0].get("reviews_data", [])
                
                logger.warning(f"No reviews found or unexpected structure for {query}")
                return []
            except Exception as e:
                logger.error(f"Outscraper API Error at skip {skip}: {str(e)}")
                return []

async def ingest_outscraper_reviews(company_obj: Any, session: AsyncSession, max_reviews: int = 10000) -> int:
    """
    Sequentially ingests reviews in batches of 500 until max_reviews is reached.
    This approach is highly stable for 10,000+ records.
    """
    client = OutscraperReviewsClient()
    batch_size = 500
    total_new_count = 0
    
    # Loop through offsets: 0, 500, 1000... up to max_reviews
    for current_skip in range(0, max_reviews, batch_size):
        logger.info(f"Fetching bag of {batch_size} reviews for {company_obj.name} (Skip: {current_skip})")
        
        raw_reviews = await client.fetch_reviews(company_obj, limit=batch_size, skip=current_skip)
        
        # If a bag returns empty, we've reached the end of Google's data
        if not raw_reviews:
            logger.info(f"No more reviews available for {company_obj.name}.")
            break

        batch_new_count = 0
        for raw in raw_reviews:
            ext_id = raw.get("review_id")
            if not ext_id:
                continue
                
            # Check for existing records to avoid duplicates
            stmt = select(Review).where(
                (Review.company_id == company_obj.id) & 
                (Review.google_review_id == ext_id)
            )
            existing = await session.execute(stmt)
            
            if existing.scalars().first():
                continue

            # Timestamp parsing with multiple format fallbacks
            raw_ts = raw.get("review_datetime_utc")
            dt_obj = None
            if raw_ts:
                try:
                    dt_obj = datetime.strptime(raw_ts, "%m/%d/%Y %H:%M:%S")
                except (ValueError, TypeError):
                    try:
                        dt_obj = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

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
            batch_new_count += 1
            total_new_count += 1

        # Commit each bag (500 records) to keep memory usage low and save progress
        if batch_new_count > 0:
            await session.commit()
            logger.info(f"Successfully saved {batch_new_count} new reviews in this batch.")
        
        # Minor throttle to respect API rate limits during large crawls
        await asyncio.sleep(1)

    return total_new_count
