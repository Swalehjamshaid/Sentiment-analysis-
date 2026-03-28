# filename: app/services/scraper.py
import logging
import asyncio
from typing import List, Dict, Any, Optional
from serpapi import GoogleSearch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.models import Company

logger = logging.getLogger("app.scraper")

# --- SERPAPI CONFIGURATION ---
SERPAPI_KEY = "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d"

async def fetch_reviews(
    company_id: int,
    session: AsyncSession,
    place_id: Optional[str] = None,
    limit: int = 50,
    **kwargs
) -> List[Dict[Any, Any]]:
    """
    STABLE 2026 SERPAPI SCRAPER:
    1. Finds Place ID for the business name.
    2. Fetches live reviews using that ID.
    """
    all_reviews = []
    try:
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        search_query = place_id if place_id else (company.name if company else "Villa The Grand Buffet")

        logger.info(f"🚀 SerpApi: Locating ID for '{search_query}'")

        # Step 1: Find Place ID
        search_params = {"engine": "google", "q": search_query, "api_key": SERPAPI_KEY, "gl": "pk"}
        def get_id():
            results = GoogleSearch(search_params).get_dict()
            return results.get("local_results", [{}])[0].get("place_id") or results.get("knowledge_graph", {}).get("place_id")

        target_id = await asyncio.to_thread(get_id)
        if not target_id:
            logger.error(f"❌ No ID found for: {search_query}")
            return []

        # Step 2: Fetch Reviews
        review_params = {"engine": "google_maps_reviews", "place_id": target_id, "api_key": SERPAPI_KEY}
        def get_data():
            return GoogleSearch(review_params).get_dict()

        results = await asyncio.to_thread(get_data)
        raw_reviews = results.get("reviews", [])

        for i, r in enumerate(raw_reviews[:limit]):
            all_reviews.append({
                "google_review_id": r.get("review_id"),
                "author_name": r.get("user", {}).get("name") or "Google User",
                "rating": int(r.get("rating", 5)),
                "text": r.get("text") or r.get("snippet") or "Verified Review",
                "google_review_time": r.get("date"),
                "review_likes": r.get("likes", 0)
            })
        logger.info(f"✅ Extracted {len(all_reviews)} reviews.")
    except Exception as e:
        logger.error(f"❌ Scraper failure: {str(e)}")
    return all_reviews
