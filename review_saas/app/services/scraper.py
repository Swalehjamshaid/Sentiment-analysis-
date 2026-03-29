import logging
import asyncio
from typing import List, Dict, Any, Optional

from serpapi import GoogleSearch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Company

logger = logging.getLogger("app.scraper")

# ------------------------------------------------------------------
# SERPAPI CONFIGURATION
# ------------------------------------------------------------------
# NOTE: Logic unchanged — still uses the same key and engine.
# You may later move this to env without affecting behavior.
SERPAPI_KEY = "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d"


async def fetch_reviews(
    company_id: int,
    session: AsyncSession,
    place_id: Optional[str] = None,
    target_limit: int = 100,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    STABLE SERPAPI FETCH (UNCHANGED LOGIC)

    Flow:
    1. Load company (for fallback name)
    2. Discover Google Place ID if not provided
    3. Fetch Google reviews via google_maps_reviews
    4. Paginate until target_limit reached
    """

    all_reviews: List[Dict[str, Any]] = []

    try:
        # --------------------------------------------------------------
        # 1. Load company (name fallback only)
        # --------------------------------------------------------------
        result = await session.execute(
            select(Company).where(Company.id == company_id)
        )
        company = result.scalar_one_or_none()

        query = (
            place_id
            if place_id
            else (company.name if company else "Villa The Grand Buffet")
        )

        logger.info(
            f"🔍 Starting review scrape | company_id={company_id} | query='{query}'"
        )

        # --------------------------------------------------------------
        # 2. Discover Place ID (UNCHANGED STRATEGY)
        # --------------------------------------------------------------
        search_params = {
            "engine": "google",
            "q": query,
            "api_key": SERPAPI_KEY,
            "gl": "pk"
        }

        def discover_place_id() -> Optional[str]:
            result = GoogleSearch(search_params).get_dict()
            local_results = result.get("local_results", [{}])
            return (
                local_results[0].get("place_id")
                or result.get("knowledge_graph", {}).get("place_id")
            )

        target_place_id = await asyncio.to_thread(discover_place_id)

        if not target_place_id:
            logger.error(f"❌ Google Place ID not found for query='{query}'")
            return []

        logger.info(f"📍 Discovered place_id={target_place_id}")

        # --------------------------------------------------------------
        # 3. Paginated Review Fetch (UNCHANGED FLOW)
        # --------------------------------------------------------------
        next_page_token: Optional[str] = None

        while len(all_reviews) < target_limit:
            params = {
                "engine": "google_maps_reviews",
                "place_id": target_place_id,
                "api_key": SERPAPI_KEY,
                "next_page_token": next_page_token
            }

            def fetch_page():
                return GoogleSearch(params).get_dict()

            results = await asyncio.to_thread(fetch_page)
            reviews = results.get("reviews", [])

            if not reviews:
                logger.info("ℹ️ No more reviews returned by SerpApi")
                break

            for r in reviews:
                if len(all_reviews) >= target_limit:
                    break

                all_reviews.append({
                    "google_review_id": r.get("review_id"),
                    "author_name": r.get("user", {}).get("name"),
                    "rating": int(r.get("rating", 5)),
                    "text": (
                        r.get("text")
                        or r.get("snippet")
                        or "No content"
                    ),
                    "google_review_time": r.get("date"),
                    "likes": r.get("likes", 0)
                })

            next_page_token = (
                results
                .get("serpapi_pagination", {})
                .get("next_page_token")
            )

            if not next_page_token:
                break

        logger.info(
            f"✅ Scraping complete | reviews_collected={len(all_reviews)}"
        )

    except Exception as exc:
        logger.exception(f"❌ Scraper error: {exc}")

    return all_reviews
