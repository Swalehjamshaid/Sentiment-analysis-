# filename: app/services/scraper.py
from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# This uses the Client class as shown in your code snippet
import serpapi

# Internal imports for your Database Models
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
    limit: int = 20,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    JSON-MAPPED CLIENT SCRAPER (2026):
    Uses the serpapi.Client to target Google Maps local results.
    Bypasses empty returns by providing local Lahore context.
    """
    
    # Get the company name from DB to ensure we are searching for the right business
    res = await session.execute(select(Company).where(Company.id == company_id))
    company = res.scalar_one_or_none()
    company_name = company.name if company else "Villa The Grand Buffet"

    logger.info(f"🚀 Starting Ingest for: {company_name}")

    try:
        # Step A: Initialize the Client
        client = serpapi.Client(api_key=SERPAPI_KEY)
        
        # Step B: Execute Search
        # We use 'google_maps' because your JSON showed local_results are found here.
        # hl=en and location are added to bypass Google's consent/cookie walls.
        results = client.search({
            "engine": "google_maps",
            "q": company_name,
            "type": "search",
            "location": "Lahore, Punjab, Pakistan",
            "hl": "en"
        })
        
        # Step C: Extract reviews from the JSON hierarchy
        formatted_reviews = []
        
        # Path 1: Check 'place_results' (Direct hit on a single business)
        if "place_results" in results:
            raw_reviews = results["place_results"].get("reviews", [])
            for r in raw_reviews:
                formatted_reviews.append({
                    "review_id": str(r.get("review_id", "id")),
                    "author_name": r.get("user", {}).get("name", "Google User"),
                    "rating": int(r.get("rating", 5)),
                    "text": r.get("snippet", "No review text.")
                })

        # Path 2: Check 'local_results' (Found in your specific JSON snippet)
        elif "local_results" in results:
            # Grab the first matching business in the list
            first_place = results["local_results"][0]
            logger.info(f"📍 Found Business: {first_place.get('title')} with {first_place.get('reviews')} reviews.")
            
            # If the search results only show a summary, we use the Place ID to get full reviews
            target_place_id = first_place.get("place_id")
            if target_place_id:
                logger.info(f"🔄 Fetching full reviews for Place ID: {target_place_id}")
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
                        "text": r.get("snippet", "No text.")
                    })

        if not formatted_reviews:
            logger.error(f"❌ Scraper found the business but no review objects were available.")
            return []

        logger.info(f"✅ SUCCESS: Formatted {len(formatted_reviews)} reviews.")
        return formatted_reviews

    except Exception as e:
        logger.error(f"❌ SCRAPER CRITICAL ERROR: {str(e)}")
        return []
