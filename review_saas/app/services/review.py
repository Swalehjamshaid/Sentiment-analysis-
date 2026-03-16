# filename: app/services/review.py

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class OutscraperReviewsClient:
    """
    Async client for Outscraper Maps Reviews API (reviews-v3).
    Fetches raw review payloads for ingestion.

    Docs:
      • https://outscraper.com/maps-reviews-api/
      • Endpoint used: /maps/reviews-v3
    """

    def __init__(self, *, base_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.OUTSCRAPER_BASE_URL).rstrip("/")
        self.api_key = (api_key or settings.OUTSCRAPER_API_KEY).strip()
        self.reviews_endpoint = f"{self.base_url}/maps/reviews-v3"

    async def fetch_reviews(
        self,
        company_obj: Any,
        *,
        max_reviews: Optional[int] = 200
    ) -> List[Dict[str, Any]]:
        """
        Fetch raw Outscraper reviews for a company.

        Parameters:
            company_obj: SQLAlchemy Company model instance.
            max_reviews: Limit for Outscraper (default 200).

        Returns:
            A list of dictionaries representing raw Outscraper payload blocks.
            These blocks are consumed by:
                app/services/google_reviews.py → ingest_outscraper_reviews()
        """
        if not self.api_key:
            raise RuntimeError(
                "OUTSCRAPER_API_KEY is missing. "
                "Set it in environment variables or .env"
            )

        # Prefer place_id when known
        query = getattr(company_obj, "google_place_id", None) or getattr(company_obj, "name", None)
        if not query:
            raise ValueError("Company object must have either google_place_id or name set.")

        # If we only have a name, enrich with address to improve accuracy
        if getattr(company_obj, "address", None) and query == company_obj.name:
            query = f"{company_obj.name}, {company_obj.address}"

        params = {
            "query": query,
            "reviewsLimit": max_reviews or 200,
            "async": "false",   # synchronous mode returns JSON immediately
        }

        headers = {
            "X-API-KEY": self.api_key
        }

        timeout = httpx.Timeout(20.0, read=60.0)

        logger.info("Outscraper request: GET %s params=%s", self.reviews_endpoint, params)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                self.reviews_endpoint,
                params=params,
                headers=headers
            )

        try:
            response.raise_for_status()
        except Exception as exc:
            logger.error("Outscraper request failed: %s", exc)
            raise

        data = response.json()

        # Outscraper may return:
        #   - [{"data":[ ... ]}]
        #   - {"data":[ ... ]}
        #   - raw lists or dict
        # Normalize to a list of blocks for the ingestion pipeline
        if isinstance(data, list):
            return data

        return [data]
