# filename: app/services/review.py

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.models import Review, Company
from app.core.db import get_session

logger = logging.getLogger(__name__)


class OutscraperReviewsClient:
    """
    Async client for Outscraper Maps Reviews API (reviews-v3).
    Fetches raw review payloads for ingestion.

    Docs:
      • https://outscraper.com/maps-reviews-api/
    """

    def __init__(self, *, base_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.OUTSCRAPER_BASE_URL).rstrip("/")
        self.api_key = (api_key or settings.OUTSCRAPER_API_KEY).strip()
        self.reviews_endpoint = f"{self.base_url}/maps/reviews-v3"

    async def fetch_reviews(
        self,
        company_obj: Company,
        *,
        max_reviews: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Fetch raw Outscraper reviews for a company.

        Parameters:
            company_obj: SQLAlchemy Company model instance.
            max_reviews: Limit for Outscraper (default 200).

        Returns:
            A list of normalized review dictionaries.
        """
        if not self.api_key:
            raise RuntimeError("OUTSCRAPER_API_KEY is missing. Set it in environment variables or .env")

        query = getattr(company_obj, "google_place_id", None) or getattr(company_obj, "name", None)
        if not query:
            raise ValueError("Company object must have either google_place_id or name set.")

        if getattr(company_obj, "address", None) and query == company_obj.name:
            query = f"{company_obj.name}, {company_obj.address}"

        params = {
            "query": query,
            "reviewsLimit": max_reviews,
            "async": "false",  # synchronous mode returns JSON immediately
        }
        headers = {"X-API-KEY": self.api_key}
        timeout = httpx.Timeout(20.0, read=60.0)

        logger.info("Fetching Outscraper reviews for '%s'", query)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(self.reviews_endpoint, params=params, headers=headers)
        try:
            response.raise_for_status()
        except Exception as exc:
            logger.error("Outscraper request failed: %s", exc)
            raise

        data = response.json()

        # Normalize data: always return a list of review dicts
        reviews_list: List[Dict[str, Any]] = []
        if isinstance(data, list):
            for block in data:
                reviews_list.extend(block.get("reviews_data", []) if isinstance(block, dict) else [])
        elif isinstance(data, dict):
            reviews_list.extend(data.get("data", []))
        return reviews_list


async def ingest_outscraper_reviews(
    company_obj: Company,
    session: Optional[AsyncSession] = None,
    client: Optional[OutscraperReviewsClient] = None,
    max_reviews: int = 200,
) -> List[Review]:
    """
    Fetch Outscraper reviews and save them to the database.

    Parameters:
        company_obj: SQLAlchemy Company instance.
        session: Optional AsyncSession; will create if not provided.
        client: Optional OutscraperReviewsClient; will create if not provided.
        max_reviews: Maximum number of reviews to fetch.

    Returns:
        List of created Review objects.
    """
    close_session = False
    if session is None:
        session = await get_session().__aenter__()
        close_session = True

    try:
        if client is None:
            client = OutscraperReviewsClient()

        raw_reviews = await client.fetch_reviews(company_obj, max_reviews=max_reviews)
        saved_reviews: List[Review] = []

        for r in raw_reviews:
            review = Review(
                company_id=company_obj.id,
                reviewer_name=r.get("author_name"),
                reviewer_profile_url=r.get("author_url"),
                rating=int(r.get("rating", 0)),
                text=r.get("text", ""),
                time=datetime.fromtimestamp(int(r.get("time", 0))) if r.get("time") else None,
                raw_data=r,
            )
            session.add(review)
            saved_reviews.append(review)

        await session.commit()
        logger.info("Saved %d reviews for company '%s'", len(saved_reviews), company_obj.name)
        return saved_reviews
    finally:
        if close_session:
            await session.__aexit__(None, None, None)
