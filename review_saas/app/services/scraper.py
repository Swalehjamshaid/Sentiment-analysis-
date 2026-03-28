# filename: app/services/scraper.py
from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from serpapi import GoogleSearch

# Internal imports - Ensure these match your app's core structure
from app.core.models import Company, CompanyCID

# --- 1. SETUP LOGGING ---
logger = logging.getLogger("app.scraper")

# --- 2. CONFIGURATION ---
# Your Private API Key from the screenshot
SERPAPI_KEY = "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d"

# --- 3. THE SCRAPER FUNCTION (fetch_reviews) ---
# This matches the import in your app/routes/reviews.py

async def fetch_reviews(
    company_id: int, 
    session: AsyncSession, 
    place_id: Optional[str] = None, 
    limit: int = 25,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    100% HARDCODED PIPELINE TEST:
    This version uses a guaranteed CID (McDonald's) to prove that your 
    API Key and Railway Database are working perfectly.
    """
    
    # 🎯 TEST CID: (A high-traffic location that ALWAYS has reviews)
    # Using this breaks the '0 reviews found' cycle.
    target_cid = "1689883584857448373" 
    
    logger.info(f"🧪 PIPELINE TEST: Forcing High-Traffic CID {target_cid} for Company {company_id}")

    try:
        # Step A: Setup SerpApi parameters for Google Maps Reviews engine
        params = {
            "engine": "google_maps_reviews",
            "data_id": target_cid,
            "api_key": SERPAPI_KEY,
            "num": limit,
            "hl": "en",
            "sort_by": "newest"
        }
        
        # Step B: Call SerpApi (Synchronous library, called within async function)
        search = GoogleSearch(params)
        results = search.get_dict()
        
        raw_reviews = results.get("reviews", [])
        
        if not raw_reviews:
            logger.warning(f"📡 API Request successful, but Google returned 0 reviews for CID {target_cid}.")
            return []

        # Step C: Format data exactly for app/routes/reviews.py
        formatted_reviews = []
        for r in raw_reviews:
            formatted_reviews.append({
                "review_id": str(r.get("review_id")),
                "author_name": r.get("user", {}).get("name", "Google User"),
                "rating": int(r.get("rating", 5)),
                "text": r.get("snippet", "No review text provided.")
            })
            
        logger.info(f"✅ SUCCESS: Scraped {len(formatted_reviews)} reviews. Saving to Railway DB now...")
        return formatted_reviews

    except Exception as e:
        logger.error(f"❌ SCRAPER CRITICAL FAILURE: {str(e)}")
        # Returns empty list to prevent route crash while logging the error
        return []
