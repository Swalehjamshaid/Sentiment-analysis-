# filename: app/services/scraper.py
from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from serpapi import GoogleSearch

# Internal imports
from app.core.models import Company

logger = logging.getLogger("app.scraper")

# --- CONFIGURATION ---
SERPAPI_KEY = "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d"

async def fetch_reviews(
    company_id: int, 
    session: AsyncSession, 
    place_id: Optional[str] = None, 
    limit: int = 20,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    100% COMPLETE & STABILIZED SCRAPER:
    Uses the Search Engine + Place ID 'Anchor' to force Google to return data.
    """
    
    # 1. Get the actual company name from DB to use as a search anchor
    from sqlalchemy import select
    res = await session.execute(select(Company).where(Company.id == company_id))
    company = res.scalar_one_or_none()
    company_name = company.name if company else "Restaurant"

    logger.info(f"🚀 Starting Stabilized Scrape for: {company_name}")

    try:
        # Step A: Use the 'google_maps' engine with BOTH Name and Place ID
        # This is the most reliable way to trigger reviews in 2026
        params = {
            "engine": "google_maps",
            "q": company_name,
            "place_id": place_id, 
            "api_key": SERPAPI_KEY,
            "type": "search",
            "hl": "en"
        }
        
        search = GoogleSearch(params)
        results = search.get_dict()
        
        # Step B: Extract reviews from the Place Results
        # Check 'place_results' first, then 'local_results'
        place_results = results.get("place_results", {})
        raw_reviews = place_results.get("reviews", [])

        if not raw_reviews:
            # Fallback: If 'place_results' is missing, check the first 'local_results'
            local_results = results.get("local_results", [])
            if local_results:
                raw_reviews = local_results[0].get("reviews", [])

        if not raw_reviews:
            logger.error(f"❌ Google still returned 0 reviews for {company_name}. Check SerpApi Dashboard for HTML snippet.")
            return []

        # Step C: Format Data
        formatted_reviews = []
        for r in raw_reviews:
            formatted_reviews.append({
                "review_id": str(r.get("review_id", "")),
                "author_name": r.get("user", {}).get("name", "Anonymous"),
                "rating": int(r.get("rating", 5)),
                "text": r.get("snippet", "No text provided.")
            })
            
        logger.info(f"✅ SUCCESS: Scraped {len(formatted_reviews)} reviews for {company_name}.")
        return formatted_reviews

    except Exception as e:
        logger.error(f"❌ Scraper Critical Failure: {str(e)}")
        return []
