# filename: app/services/scraper.py
from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from serpapi import GoogleSearch

# Internal imports - Required for the session to understand the models
from app.core.models import Company, CompanyCID

# --- 1. SETUP LOGGING ---
logger = logging.getLogger("app.scraper")

# --- 2. CONFIGURATION ---
# Your verified SerpApi Key from your history
SERPAPI_KEY = "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d"

# --- 3. MAIN SCRAPER FUNCTION (fetch_reviews) ---
# This is the function your app/routes/reviews.py is looking for.

async def fetch_reviews(
    company_id: int, 
    session: AsyncSession, 
    place_id: Optional[str] = None, 
    limit: int = 50,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    TEST MODE: Hardcoded CID to bypass 'No CID available' errors.
    This allows us to verify if the Database and API are working.
    """
    
    # 🎯 FORCE CID for Villa The Grand Buffet
    # This matches the location currently causing the 'Aborting' error in your logs.
    target_cid = "2467657989938831316" 
    
    logger.info(f"🧪 TEST MODE: Forcing CID {target_cid} for Company ID {company_id}")

    try:
        # Step A: Setup SerpApi parameters
        params = {
            "engine": "google_maps_reviews",
            "data_id": target_cid,
            "api_key": SERPAPI_KEY,
            "num": limit,
            "hl": "en",
            "sort_by": "newest"
        }
        
        # Step B: Call SerpApi
        # Note: The serpapi-python library is synchronous, we call it directly.
        search = GoogleSearch(params)
        results = search.get_dict()
        
        raw_reviews = results.get("reviews", [])
        
        if not raw_reviews:
            logger.warning(f"📡 API Request successful, but no reviews were found for CID {target_cid}")
            return []

        # Step C: Format the data for the FastAPI route
        # Your route expects: review_id, author_name, rating, and text.
        formatted_reviews = []
        for r in raw_reviews:
            formatted_reviews.append({
                "review_id": r.get("review_id"),
                "author_name": r.get("user", {}).get("name", "Anonymous"),
                "rating": r.get("rating", 0),
                "text": r.get("snippet", "")
            })
            
        logger.info(f"✅ TEST SUCCESS: Scraped {len(formatted_reviews)} reviews for Company {company_id}")
        return formatted_reviews

    except Exception as e:
        logger.error(f"❌ TEST MODE CRITICAL ERROR: {str(e)}")
        # Return empty list so the route doesn't crash, but shows the error in logs
        return []

# --- 4. OPTIONAL: Helper to resolve CID (Keeping it for future non-test use) ---
async def resolve_cid_via_serpapi(place_id: str) -> Optional[str]:
    try:
        params = {"engine": "google_maps", "q": place_id, "api_key": SERPAPI_KEY}
        search = GoogleSearch(params)
        results = search.get_dict()
        return results.get("place_results", {}).get("data_id")
    except:
        return None
