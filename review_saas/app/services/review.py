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

    async def fetch_reviews(self, company_obj: Any, max_reviews: int = 200) -> List[Dict[str, Any]]:
        query = getattr(company_obj, "google_place_id", None) or getattr(company_obj, "name", None)
        params = {"query": query, "reviewsLimit": max_reviews, "async": "false"}
        headers = {"X-API-KEY": self.api_key}

        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, read=60.0)) as client:
            response = await client.get(self.reviews_endpoint, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            # Extracting the list of reviews from the first result block
            return data[0].get("reviews_data", []) if data else []

async def ingest_outscraper_reviews(company_obj: Any, session: AsyncSession, max_reviews: int = 200) -> int:
    client = OutscraperReviewsClient()
    raw_reviews = await client.fetch_reviews(company_obj, max_reviews=max_reviews)
    
    new_count = 0
    for raw in raw_reviews:
        # Deduplication check (ensure your Review model has review_id_external)
        ext_id = raw.get("review_id")
        stmt = select(Review).where(Review.review_id_external == ext_id)
        existing = await session.execute(stmt)
        
        if existing.scalars().first():
            continue

        # Create and add the new record
        new_review = Review(
            company_id=company_obj.id,
            review_id_external=ext_id,
            author_name=raw.get("author_title"),
            content=raw.get("review_text"),
            rating=raw.get("review_rating"),
            date=datetime.fromisoformat(raw.get("review_datetime_utc").replace("Z", "+00:00")).date()
        )
        session.add(new_review)
        new_count += 1

    if new_count > 0:
        await session.commit() 
    return new_count
