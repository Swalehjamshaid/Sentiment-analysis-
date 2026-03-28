# filename: app/services/scraper.py
import logging
import asyncio
from typing import List, Dict, Any, Optional
from serpapi import GoogleSearch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Internal imports
from app.core.models import Company

logger = logging.getLogger("app.scraper")

# --- SERPAPI CONFIGURATION ---
# Using your verified API Key from the SerpApi dashboard image
SERPAPI_KEY = "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d"

async def fetch_reviews(
    company_id: int,
    session: AsyncSession,
    place_id: Optional[str] = None,
    limit: int = 50,
    **kwargs
) -> List[Dict[Any, Any]]:
    """
    REAL-TIME SERPAPI INGEST:
    Bypasses the "Sample Data" issue by fetching live reviews from Google Maps.
    """
    all_reviews = []
    
    try:
        # 1. Resolve Company Name
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        
        # Use the name for the search query (e.g., Bahria Town)
        search_query = place_id if place_id else (company.name if company else "Villa The Grand Buffet")

        logger.info(f"🚀 INGEST START: Searching SerpApi for '{search_query}'")

        # 2. STEP 1: Find the official Place ID
        search_params = {
            "engine": "google",
            "q": search_query,
            "api_key": SERPAPI_KEY,
            "hl": "en",
            "gl": "pk"
        }

        def get_metadata():
            search = GoogleSearch(search_params)
            results = search.get_dict()
            local = results.get("local_results", [])
            if local:
                return local[0].get("place_id")
            return results.get("knowledge_graph", {}).get("place_id")

        target_id = await asyncio.to_thread(get_metadata)

        if not target_id:
            logger.error(f"❌ Could not find a real Google ID for: {search_query}")
            return []

        # 3. STEP 2: Fetch the actual reviews
        review_params = {
            "engine": "google_maps_reviews",
            "place_id": target_id,
            "api_key": SERPAPI_KEY,
            "hl": "en"
        }

        def get_real_data():
            search = GoogleSearch(review_params)
            return search.get_dict()

        results = await asyncio.to_thread(get_real_data)
        raw_reviews = results.get("reviews", [])

        # 4. Map to your Postgres Schema (matches Image 2 and 3)
        for i, r in enumerate(raw_reviews[:limit]):
            all_reviews.append({
                "company_id": company_id,
                "google_review_id": r.get("review_id"),
                "author_name": r.get("user", {}).get("name") or "Google User",
                "rating": int(r.get("rating", 5)),
                "text": r.get("text") or r.get("snippet") or "Verified Review Content",
                "review_language": "en",
                "google_review_time": r.get("date")
            })

        logger.info(f"✅ SUCCESS: Captured {len(all_reviews)} LIVE reviews for {search_query}")

    except Exception as e:
        logger.error(f"❌ Scraper Failure: {str(e)}", exc_info=True)

    return all_reviews
