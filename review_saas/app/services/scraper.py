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
SERPAPI_KEY = "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d"

# --- FIXED: Renamed to match the import 'fetch_reviews_from_google' ---
async def fetch_reviews_from_google(
    place_id: Optional[str] = None,
    company_id: Optional[int] = None,
    session: Optional[AsyncSession] = None,
    target_limit: int = 100,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    FIXED SCRAPER:
    Checks if query is already a Place ID to avoid discovery failure.
    Matches the function name expected by app/routes/reviews.py.
    """

    all_reviews: List[Dict[str, Any]] = []

    try:
        # 1. Determine the target Place ID
        # Priority: Function Argument > Database Record
        target_place_id = place_id
        
        if not target_place_id and company_id and session:
            result = await session.execute(
                select(Company).where(Company.id == company_id)
            )
            company = result.scalar_one_or_none()
            target_place_id = company.google_place_id if company else None

        # --------------------------------------------------------------
        # 2. Smart Discovery (FIXED)
        # --------------------------------------------------------------
        # If target_place_id starts with 'ChIJ', it's already a valid ID. 
        # We skip the discovery search entirely.
        
        if not target_place_id or not target_place_id.startswith("ChIJ"):
            # Fallback to search by name if ID is missing or malformed
            query = target_place_id or "Villa The Grand Buffet"
            logger.info(f"🔍 Searching for Place ID for query: '{query}'")
            
            search_params = {
                "engine": "google",
                "q": query,
                "api_key": SERPAPI_KEY,
                "gl": "pk"
            }

            def discover_id():
                search = GoogleSearch(search_params)
                res = search.get_dict()
                # Check Local Results or Knowledge Graph
                return (
                    res.get("local_results", [{}])[0].get("place_id") or 
                    res.get("knowledge_graph", {}).get("place_id")
                )

            target_place_id = await asyncio.to_thread(discover_id)

        if not target_place_id:
            logger.error("❌ Could not determine a valid Google Place ID")
            return []

        logger.info(f"📍 Using Place ID for Fetch: {target_place_id}")

        # --------------------------------------------------------------
        # 3. Paginated Review Fetch
        # --------------------------------------------------------------
        next_page_token: Optional[str] = None

        while len(all_reviews) < target_limit:
            params = {
                "engine": "google_maps_reviews",
                "place_id": target_place_id,
                "api_key": SERPAPI_KEY,
                "next_page_token": next_page_token
            }

            results = await asyncio.to_thread(lambda: GoogleSearch(params).get_dict())
            reviews = results.get("reviews", [])

            if not reviews:
                logger.info("ℹ️ No more reviews returned by SerpApi")
                break

            for r in reviews:
                if len(all_reviews) >= target_limit:
                    break
                
                # Mapping SerpApi structure to our Database structure
                all_reviews.append({
                    "google_review_id": r.get("review_id"),
                    "author_name": r.get("user", {}).get("name"),
                    "rating": int(r.get("rating", 5)),
                    "text": r.get("text") or r.get("snippet") or "No content",
                    "google_review_time": r.get("date"),
                    "likes": r.get("likes", 0)
                })

            next_page_token = results.get("serpapi_pagination", {}).get("next_page_token")
            if not next_page_token:
                break

        logger.info(f"✅ Scraping complete | reviews_collected={len(all_reviews)}")

    except Exception as exc:
        logger.error(f"❌ Scraper critical failure: {exc}")

    return all_reviews
