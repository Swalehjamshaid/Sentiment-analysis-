# filename: app/services/scraper.py
import logging
import asyncio
from typing import List, Dict, Any, Optional
from serpapi import GoogleSearch # The core library
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.models import Company

logger = logging.getLogger("app.scraper")

# --- SERPAPI CONFIGURATION ---
# Using your verified key: f9f41e45...
SERPAPI_KEY = "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d"

async def fetch_reviews(
    company_id: int,
    session: AsyncSession,
    place_id: Optional[str] = None,
    limit: int = 50,
    **kwargs
) -> List[Dict[Any, Any]]:
    """
    Fetches exact Google Maps review data using the SerpApi Python SDK.
    """
    all_reviews = []
    
    try:
        # 1. Resolve Company Name for the search
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        search_query = place_id if place_id else (company.name if company else "Villa The Grand Buffet")

        # 2. STEP 1: Find the official Place ID (The 'Unique Fingerprint' of the business)
        # We do this to ensure we don't get the "Missing place_id" error again.
        search_params = {
            "engine": "google",
            "q": search_query,
            "api_key": SERPAPI_KEY,
            "gl": "pk"
        }

        def get_metadata():
            search = GoogleSearch(search_params)
            results = search.get_dict()
            # Check local results or knowledge graph for the ID
            return results.get("local_results", [{}])[0].get("place_id") or \
                   results.get("knowledge_graph", {}).get("place_id")

        target_id = await asyncio.to_thread(get_metadata)

        if not target_id:
            logger.error(f"❌ Could not find an official Google ID for: {search_query}")
            return []

        # 3. STEP 2: Fetch the Exact Review Data
        review_params = {
            "engine": "google_maps_reviews",
            "place_id": target_id,
            "api_key": SERPAPI_KEY,
            "hl": "en"
        }

        def get_live_reviews():
            search = GoogleSearch(review_params)
            return search.get_dict()

        results = await asyncio.to_thread(get_live_reviews)
        raw_reviews = results.get("reviews", [])

        # 4. MAP DATA TO YOUR DATABASE COLUMNS
        for i, r in enumerate(raw_reviews[:limit]):
            all_reviews.append({
                "google_review_id": r.get("review_id"),
                "author_name": r.get("user", {}).get("name") or "Google User",
                "rating": int(r.get("rating", 5)),
                "text": r.get("text") or r.get("snippet") or "No text content.",
                "google_review_time": r.get("date"),
                "review_likes": r.get("likes", 0),
                "author_id": r.get("user", {}).get("contributor_id")
            })

        logger.info(f"✅ Success: Fetched {len(all_reviews)} reviews for {search_query}")

    except Exception as e:
        logger.error(f"❌ SerpApi SDK Failure: {str(e)}")
        
    return all_reviews
