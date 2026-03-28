# filename: app/services/scraper.py
from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Standard import for the google-search-results library
from serpapi import GoogleSearch 

# Internal imports for Database Models
from app.core.models import Company

# --- 1. SETUP LOGGING ---
logger = logging.getLogger("app.scraper")

# --- 2. CONFIGURATION ---
# Your verified SerpApi Key
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
    STABILIZED DOUBLE-PASS SCRAPER:
    Pass 1: Identifies the correct business and retrieves the Place ID.
    Pass 2: Uses the Place ID to pull the deep 'reviews' array.
    """
    
    # Retrieve the company name from the database
    res = await session.execute(select(Company).where(Company.id == company_id))
    company = res.scalar_one_or_none()
    company_name = company.name if company else "Villa The Grand Buffet"

    logger.info(f"🚀 Starting Ingest for: {company_name}")

    try:
        # --- STEP 1: FIND THE BUSINESS ID ---
        search_params = {
            "engine": "google_maps",
            "q": company_name,
            "type": "search",
            "location": "Lahore, Punjab, Pakistan",
            "hl": "en",
            "api_key": SERPAPI_KEY
        }
        
        search = GoogleSearch(search_params)
        results = search.get_dict()
        
        target_place_id = None
        
        # Check if we got a direct Business Profile or a list of search results
        if "place_results" in results:
            target_place_id = results["place_results"].get("place_id")
        elif "local_results" in results and len(results["local_results"]) > 0:
            # We pick the first local result as the most relevant match
            target_place_id = results["local_results"][0].get("place_id")

        if not target_place_id:
            logger.error(f"❌ Verification Failed: Could not find a Place ID for {company_name}")
            return []

        # --- STEP 2: FETCH THE ACTUAL REVIEWS ---
        logger.info(f"🎯 Business Verified (ID: {target_place_id}). Fetching reviews...")
        
        review_params = {
            "engine": "google_maps_reviews",
            "place_id": target_place_id,
            "api_key": SERPAPI_KEY,
            "hl": "en",
            "sort_by": "newestFirst" # Critical for 2026 data stability
        }
        
        review_search = GoogleSearch(review_params)
        review_results = review_search.get_dict()
        raw_reviews = review_results.get("reviews", [])

        # --- STEP 3: FORMAT FOR DATABASE ---
        formatted_reviews = []
        for r in raw_reviews:
            formatted_reviews.append({
                "review_id": str(r.get("review_id", "id_missing")),
                "author_name": r.get("user", {}).get("name", "Google User"),
                "rating": int(r.get("rating", 5)),
                "text": r.get("snippet", "No text provided.")
            })
            
        logger.info(f"✅ SUCCESS: {len(formatted_reviews)} reviews retrieved for {company_name}.")
        return formatted_reviews

    except Exception as e:
        logger.error(f"❌ SCRAPER CRITICAL ERROR: {str(e)}")
        return []
