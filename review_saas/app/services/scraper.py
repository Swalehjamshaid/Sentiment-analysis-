# filename: app/services/scraper.py
import logging
import asyncio
from typing import List, Dict, Any, Optional
from serpapi import GoogleSearch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Internal imports
from app.core.models import Company

# Define the scraper-specific logger
logger = logging.getLogger("app.scraper")

# --- SERPAPI CONFIGURATION ---
# Using your verified API Key from the SerpApi dashboard image
SERPAPI_KEY = "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d"

async def fetch_reviews(
    company_id: int,
    session: AsyncSession,
    place_id: Optional[str] = None,
    limit: int = 30,
    **kwargs
) -> List[Dict[Any, Any]]:
    """
    STABLE 2026 SERPAPI SCRAPER:
    1. Uses 'google' engine to find the official Place ID for the company name.
    2. Uses 'google_maps_reviews' engine with that Place ID to get the data.
    This bypasses all 401 Proxy errors and 'Malformed URL' issues.
    """
    all_reviews = []
    target_name = "Unknown"

    try:
        # 1. Resolve Company Details from Database
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()

        if not company:
            logger.error(f"❌ Company with id {company_id} not found in DB.")
            return []

        target_name = company.name
        # Use provided place_id (if it's a name) or the database name
        search_query = place_id if place_id else target_name
        
        logger.info(f"🚀 SerpApi Step 1: Locating official ID for '{search_query}'")

        # 2. STEP 1: Find the official Google Place ID
        # This prevents the 'data_id or place_id missing' error
        search_params = {
            "engine": "google",
            "q": search_query,
            "api_key": SERPAPI_KEY,
            "hl": "en",
            "gl": "pk"
        }

        def run_id_lookup():
            search = GoogleSearch(search_params)
            results = search.get_dict()
            # Look in local_results first, then knowledge_graph
            local = results.get("local_results", [])
            if local:
                return local[0].get("place_id")
            return results.get("knowledge_graph", {}).get("place_id")

        discovered_place_id = await asyncio.to_thread(run_id_lookup)

        if not discovered_place_id:
            logger.error(f"❌ Could not find a Google Place ID for: {search_query}")
            return []

        logger.info(f"✅ ID Found: {discovered_place_id}. Step 2: Fetching live reviews...")

        # 3. STEP 2: Fetch the actual reviews using the Discovered ID
        review_params = {
            "engine": "google_maps_reviews",
            "place_id": discovered_place_id,
            "api_key": SERPAPI_KEY,
            "hl": "en"
        }

        def run_review_fetch():
            search = GoogleSearch(review_params)
            return search.get_dict()

        results = await asyncio.to_thread(run_review_fetch)

        # 4. Check for SerpApi Errors
        if "error" in results:
            logger.error(f"❌ SerpApi Engine Error: {results['error']}")
            return []

        # 5. Extract and Format Reviews for the Dashboard
        raw_reviews = results.get("reviews", [])
        for i, r in enumerate(raw_reviews[:limit]):
            all_reviews.append({
                "review_id": r.get("review_id", f"SERP-{company_id}-{i}"),
                "author_name": r.get("user", {}).get("name", "Google User"),
                "rating": int(r.get("rating", 5)),
                "text": r.get("snippet") or r.get("text") or "No review text available.",
                "date": r.get("date"),
                "likes": r.get("likes", 0)
            })

        logger.info(f"✅ AgentQL/SerpApi Success: Extracted {len(all_reviews)} reviews.")

    except Exception as e:
        logger.error(f"❌ Scraper critical failure for {target_name}: {str(e)}", exc_info=True)

    logger.info(f"🏁 Scraper finished for {target_name}: Captured {len(all_reviews)} reviews.")
    return all_reviews
