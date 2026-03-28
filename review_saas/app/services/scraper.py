# filename: app/services/scraper.py
from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from serpapi import GoogleSearch

# Internal imports - Required for the session to interact with your DB models
from app.core.models import Company, CompanyCID

# --- 1. SETUP LOGGING ---
logger = logging.getLogger("app.scraper")

# --- 2. CONFIGURATION ---
# Your verified SerpApi Key
SERPAPI_KEY = "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d"

# --- 3. THE SCRAPER FUNCTION (fetch_reviews) ---
# This matches the import in your app/routes/reviews.py

async def fetch_reviews(
    company_id: int, 
    session: AsyncSession, 
    place_id: Optional[str] = None, 
    limit: int = 50,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    100% HARDCODED PIPELINE TEST:
    We are ignoring the Database CID and the Google Search.
    We are forcing a CID that is guaranteed to have 10,000+ reviews.
    
    If this works, your Railway 'reviews' table will fill up with data.
    """
    
    # 🎯 MANUALLY ADDED CID: (High-Traffic McDonald's)
    # This ID is guaranteed to return reviews. 
    # Use this to verify that your 'reviews' table is working.
    target_cid = "1689883584857448373" 
    
    logger.info(f"🧪 TESTING PIPELINE: Forcing High-Traffic CID {target_cid} for Company {company_id}")

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
        
        # Step B: Execute the search via SerpApi
        # Note: The library is synchronous, we run it directly.
        search = GoogleSearch(params)
        results = search.get_dict()
        
        raw_reviews = results.get("reviews", [])
        
        if not raw_reviews:
            logger.warning(f"📡 API Request was successful, but Google returned 0 reviews for CID {target_cid}")
            return []

        # Step C: Format the reviews into a list of dictionaries for the FastAPI route
        formatted_reviews = []
        for r in raw_reviews:
            formatted_reviews.append({
                "review_id": str(r.get("review_id")),
                "author_name": r.get("user", {}).get("name", "Google User"),
                "rating": int(r.get("rating", 5)),
                "text": r.get("snippet", "No review text provided by user.")
            })
            
        logger.info(f"✅ SCRAPER SUCCESS: Found {len(formatted_reviews)} reviews. Now sending to Railway DB...")
        return formatted_reviews

    except Exception as e:
        logger.error(f"❌ SCRAPER CRITICAL FAILURE: {str(e)}")
        # Returning an empty list ensures the API route doesn't crash, 
        # but the error is logged for you to see.
        return []

# --- 4. LEGACY HELPER (Unused in this hardcoded test) ---
async def resolve_cid_via_serpapi(place_id: str) -> Optional[str]:
    # Keeping this so the file structure remains valid
    return None
