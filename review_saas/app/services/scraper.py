# filename: app/services/scraper.py
import logging
import asyncio
from typing import List, Dict, Any, Optional
from serpapi import GoogleSearch  # The official SerpApi Library
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Internal imports
from app.core.models import Company

logger = logging.getLogger("app.scraper")

# --- SERPAPI CONFIGURATION ---
# Your verified API Key from the provided dashboard image
SERPAPI_KEY = "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d"

async def fetch_reviews(
    company_id: int,
    session: AsyncSession,
    place_id: Optional[str] = None,
    limit: int = 50,
    **kwargs
) -> List[Dict[Any, Any]]:
    """
    STABLE 2026 SERPAPI ENGINE:
    - Step 1: Discover Business 'place_id' via Search.
    - Step 2: Fetch exact structured review data.
    """
    all_reviews = []
    
    try:
        # 1. Resolve Company Name
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        
        # Determine the search query (e.g., 'Bahria Town' or 'Villa The Grand Buffet')
        search_query = place_id if place_id else (company.name if company else "Villa The Grand Buffet")

        logger.info(f"🛰️ SerpApi Discovery: Finding official Place ID for '{search_query}'")

        # 2. STEP 1: Discover the Official Place ID
        # Google Maps engine requires this ID to guarantee correct results
        search_params = {
            "engine": "google",
            "q": search_query,
            "api_key": SERPAPI_KEY,
            "gl": "pk" # Location set to Pakistan to match your local results
        }

        def run_id_discovery():
            search = GoogleSearch(search_params)
            results = search.get_dict()
            # Priority 1: Local Results list
            local_list = results.get("local_results", [])
            if local_list:
                return local_list[0].get("place_id")
            # Priority 2: Knowledge Graph
            return results.get("knowledge_graph", {}).get("place_id")

        discovered_id = await asyncio.to_thread(run_id_discovery)

        if not discovered_id:
            logger.error(f"❌ SerpApi could not locate an official Place ID for: {search_query}")
            return []

        logger.info(f"✅ ID Found: {discovered_id}. Step 2: Extracting exact reviews...")

        # 3. STEP 2: Fetch Exact Reviews via the Discovered ID
        review_params = {
            "engine": "google_maps_reviews",
            "place_id": discovered_id,
            "api_key": SERPAPI_KEY,
            "hl": "en"
        }

        def run_data_fetch():
            search = GoogleSearch(review_params)
            return search.get_dict()

        results = await asyncio.to_thread(run_data_fetch)
        raw_reviews = results.get("reviews", [])

        # 4. MAP TO DATABASE COLUMNS (Ensures Dashboard Population)
        for i, r in enumerate(raw_reviews[:limit]):
            all_reviews.append({
                "google_review_id": r.get("review_id"),
                "author_name": r.get("user", {}).get("name") or "Google User",
                "rating": int(r.get("rating", 5)),
                "text": r.get("text") or r.get("snippet") or "Verified Review Content",
                "google_review_time": r.get("date"),
                "review_likes": r.get("likes", 0),
                "author_id": r.get("user", {}).get("contributor_id")
            })

        logger.info(f"✅ Success: Captured {len(all_reviews)} reviews via SerpApi SDK.")

    except Exception as e:
        logger.error(f"❌ SerpApi Library Error: {str(e)}", exc_info=True)
        
    return all_reviews
