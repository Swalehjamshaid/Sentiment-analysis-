# filename: app/services/scraper.py
from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# This matches the library shown in your SerpApi dashboard screenshot
import serpapi

# Internal imports for your Database Models
from app.core.models import Company

# --- 1. SETUP LOGGING ---
logger = logging.getLogger("app.scraper")

# --- 2. CONFIGURATION ---
# Your Private API Key from the screenshot (f9f4...0e8d)
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
    STABILIZED CLIENT SCRAPER:
    Uses the serpapi.Client approach from your screenshot.
    Targets Google Maps specifically to retrieve review text.
    """
    
    # 1. Retrieve the company name from your DB to use as a search anchor
    res = await session.execute(select(Company).where(Company.id == company_id))
    company = res.scalar_one_or_none()
    
    # Anchor name for search context
    company_name = company.name if company else "Villa The Grand Buffet"

    logger.info(f"🚀 Starting Client-based Ingest for: {company_name}")

    try:
        # Step A: Initialize the Client exactly as shown in your screenshot
        client = serpapi.Client(api_key=SERPAPI_KEY)
        
        # Step B: Perform the Search
        # We use 'google_maps' as the engine to find the place_id and reviews
        # hl=en and location are added to ensure Google returns reviews in English
        results = client.search({
            "engine": "google_maps",
            "q": company_name,
            "type": "search",
            "location": "Lahore, Punjab, Pakistan",
            "hl": "en"
        })
        
        formatted_reviews = []
        
        # Path 1: Extract from 'place_results' (Direct Hit)
        if "place_results" in results:
            raw_reviews = results["place_results"].get("reviews", [])
            for r in raw_reviews:
                formatted_reviews.append({
                    "review_id": str(r.get("review_id", "id_missing")),
                    "author_name": r.get("user", {}).get("name", "Google User"),
                    "rating": int(r.get("rating", 5)),
                    "text": r.get("snippet", "No review text provided.")
                })

        # Path 2: Extract from 'local_results' (List view, as seen in your JSON snippet)
        elif "local_results" in results:
            first_place = results["local_results"][0]
            target_place_id = first_place.get("place_id")
            
            if target_place_id:
                logger.info(f"🔄 Found Place ID: {target_place_id}. Fetching deep review list...")
                # Call the specific reviews engine using the found ID
                review_results = client.search({
                    "engine": "google_maps_reviews",
                    "place_id": target_place_id,
                    "hl": "en"
                })
                for r in review_results.get("reviews", []):
                    formatted_reviews.append({
                        "review_id": str(r.get("review_id")),
                        "author_name": r.get("user", {}).get("name", "Anonymous"),
                        "rating": int(r.get("rating", 5)),
                        "text": r.get("snippet", "No review text.")
                    })

        if not formatted_reviews:
            logger.error(f"❌ Scraper found the business but no reviews were available in the response.")
            return []

        logger.info(f"✅ SUCCESS: Formatted {len(formatted_reviews)} reviews for processing.")
        return formatted_reviews

    except Exception as e:
        logger.error(f"❌ SCRAPER CRITICAL ERROR: {str(e)}")
        return []
