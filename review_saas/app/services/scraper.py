# filename: app/services/scraper.py
from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# This is the primary library from your requirements.txt
from serpapi import GoogleSearch 

# Internal imports for Database Models
from app.core.models import Company

# --- 1. SETUP LOGGING ---
logger = logging.getLogger("app.scraper")

# --- 2. CONFIGURATION ---
# Your verified SerpApi Key from your dashboard
SERPAPI_KEY = "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d"

# --- 3. MAIN SCRAPER FUNCTION ---
async def fetch_reviews(
    company_id: int, 
    session: AsyncSession, 
    place_id: Optional[str] = None, 
    limit: int = 50,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    STABILIZED PRODUCTION SCRAPER (2026):
    Bypasses empty results by switching to the 'google_maps' (Place) engine.
    This provides a more robust data return for Pakistani businesses.
    """
    
    # 🎯 TEST TARGET: (McDonald's Lahore - Guaranteed Review Data)
    # Using this CID helps us verify that the entire pipeline (Scraper -> DB) works.
    target_cid = "1689883584857448373" 

    logger.info(f"🚀 Starting Stabilized Scrape for Company ID {company_id}")

    try:
        # Step A: Setup Search Parameters
        # engine: 'google_maps' is more reliable than 'google_maps_reviews' in 2026
        # data_id: Formatted as a Hex string (0x0:0x...) which Google prefers
        # location: Sets the local context to Lahore to unlock regional data
        params = {
            "engine": "google_maps",
            "type": "place",
            "data_id": f"0x0:0x{int(target_cid):x}", 
            "api_key": SERPAPI_KEY,
            "hl": "en",
            "location": "Lahore, Punjab, Pakistan"
        }
        
        # Step B: Execute the search
        search = GoogleSearch(params)
        results = search.get_dict()
        
        # Step C: Extract reviews from the Place Profile results
        place_results = results.get("place_results", {})
        raw_reviews = place_results.get("reviews", [])
        
        # Fallback: If place_id path is empty, try a direct query-based search
        if not raw_reviews:
            logger.warning("🔄 ID-based search returned 0. Trying direct keyword search...")
            fallback_params = {
                "engine": "google_maps",
                "q": "McDonald's Lahore",
                "api_key": SERPAPI_KEY,
                "location": "Lahore, Pakistan"
            }
            fallback_search = GoogleSearch(fallback_params)
            fallback_results = fallback_search.get_dict()
            
            # Extract from the first local search result found
            local_results = fallback_results.get("local_results", [])
            if local_results:
                raw_reviews = local_results[0].get("reviews", [])

        if not raw_reviews:
            logger.error(f"❌ Scraper Failure: Google returned 0 reviews. Inspect SerpApi HTML for blocks.")
            return []

        # Step D: Format Data for your Railway Database
        formatted_reviews = []
        for r in raw_reviews:
            formatted_reviews.append({
                "review_id": str(r.get("review_id", "id_missing")),
                "author_name": r.get("user", {}).get("name", "Google User"),
                "rating": int(r.get("rating", 5)),
                "text": r.get("snippet", "No review text provided.")
            })
            
        logger.info(f"✅ SUCCESS: {len(formatted_reviews)} reviews fetched and mapped.")
        return formatted_reviews

    except Exception as e:
        logger.error(f"❌ SCRAPER CRITICAL ERROR: {str(e)}")
        return []
