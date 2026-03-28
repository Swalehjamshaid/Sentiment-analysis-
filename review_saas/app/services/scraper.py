# filename: app/services/scraper.py
import logging
import asyncio
from typing import List, Dict, Any, Optional
from serpapi import GoogleSearch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.models import Company

logger = logging.getLogger("app.scraper")

# --- SERPAPI CONFIGURATION ---
SERPAPI_KEY = "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d"

async def fetch_reviews(
    company_id: int,
    session: AsyncSession,
    place_id: Optional[str] = None,
    target_limit: int = 100,
    **kwargs
) -> List[Dict[Any, Any]]:
    """
    STABLE SERPAPI FETCH: 
    Loops through pages to get up to 100 reviews.
    """
    all_reviews = []
    try:
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        query = place_id if place_id else (company.name if company else "Villa The Grand Buffet")

        # Step 1: Discover Place ID
        search_params = {"engine": "google", "q": query, "api_key": SERPAPI_KEY, "gl": "pk"}
        
        def get_id():
            results = GoogleSearch(search_params).get_dict()
            local = results.get("local_results", [{}])
            return local[0].get("place_id") or results.get("knowledge_graph", {}).get("place_id")

        target_id = await asyncio.to_thread(get_id)
        if not target_id:
            logger.error(f"❌ ID not found for {query}")
            return []

        # Step 2: Paginated Fetch
        next_page_token = None
        while len(all_reviews) < target_limit:
            params = {
                "engine": "google_maps_reviews",
                "place_id": target_id,
                "api_key": SERPAPI_KEY,
                "next_page_token": next_page_token
            }
            
            def fetch_data():
                return GoogleSearch(params).get_dict()

            results = await asyncio.to_thread(fetch_data)
            reviews = results.get("reviews", [])
            if not reviews:
                break

            for r in reviews:
                if len(all_reviews) < target_limit:
                    all_reviews.append({
                        "google_review_id": r.get("review_id"),
                        "author_name": r.get("user", {}).get("name"),
                        "rating": int(r.get("rating", 5)),
                        "text": r.get("text") or r.get("snippet") or "No content",
                        "google_review_time": r.get("date"),
                        "likes": r.get("likes", 0)
                    })

            next_page_token = results.get("serpapi_pagination", {}).get("next_page_token")
            if not next_page_token:
                break

    except Exception as e:
        logger.error(f"❌ Scraper error: {e}")
    
    return all_reviews
