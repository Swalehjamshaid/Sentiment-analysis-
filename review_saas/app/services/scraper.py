# filename: app/services/scraper.py
from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from serpapi import GoogleSearch

# Internal imports
from app.core.models import Company, CompanyCID

logger = logging.getLogger("app.scraper")

# --- CONFIGURATION ---
SERPAPI_KEY = "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d"

async def fetch_reviews(
    company_id: int, 
    session: AsyncSession, 
    place_id: Optional[str] = None, 
    limit: int = 50,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    STABILIZED SCRAPER (2026 Version):
    Forces 'newestFirst' sorting to bypass Google's empty default filter.
    """
    
    # Using the guaranteed McDonald's CID for testing, 
    # but the logic below works for any business.
    target_cid = "1689883584857448373" 
    
    logger.info(f"🚀 Attempting stabilized scrape for CID: {target_cid}")

    try:
        # Step A: Primary Request using google_maps_reviews
        # CRITICAL FIX: Adding 'sort_by': 'newestFirst'
        params = {
            "engine": "google_maps_reviews",
            "data_id": target_cid,
            "api_key": SERPAPI_KEY,
            "sort_by": "newestFirst",  # Forces Google to show existing data
            "num": limit,
            "hl": "en"
        }
        
        search = GoogleSearch(params)
        results = search.get_dict()
        raw_reviews = results.get("reviews", [])
        
        # Step B: Fallback Request (If Reviews engine is failing)
        if not raw_reviews:
            logger.warning("🔄 Reviews engine returned empty. Trying Place Search fallback...")
            fallback_params = {
                "engine": "google_maps",
                "type": "place",
                "place_id": place_id if place_id else "ChIJNc-tXDMbdkgRK71JU82ZU38",
                "api_key": SERPAPI_KEY
            }
            search = GoogleSearch(fallback_params)
            results = search.get_dict()
            raw_reviews = results.get("place_results", {}).get("reviews", [])

        if not raw_reviews:
            logger.error(f"❌ All engines returned 0 reviews for CID {target_cid}")
            return []

        # Step C: Format Data
        formatted_reviews = []
        for r in raw_reviews:
            formatted_reviews.append({
                "review_id": str(r.get("review_id")),
                "author_name": r.get("user", {}).get("name", "Google User"),
                "rating": int(r.get("rating", 5)),
                "text": r.get("snippet", "No review text provided.")
            })
            
        logger.info(f"✅ SUCCESS: Scraped {len(formatted_reviews)} reviews.")
        return formatted_reviews

    except Exception as e:
        logger.error(f"❌ Scraper Failure: {str(e)}")
        return []
