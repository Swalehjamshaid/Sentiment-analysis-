# filename: app/services/scraper.py
import logging
import asyncio
from typing import List, Dict, Any, Optional
from serpapi import GoogleSearch # Ensure this is in requirements.txt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Internal imports
from app.core.models import Company

logger = logging.getLogger("app.scraper")

# --- SERPAPI CONFIGURATION ---
# Your API Key from the image you provided
SERPAPI_KEY = "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d"

async def fetch_reviews(
    company_id: int,
    session: AsyncSession,
    place_id: Optional[str] = None,
    limit: int = 30,
    **kwargs
) -> List[Dict[Any, Any]]:
    """
    PROFESSIONAL SERPAPI INGEST:
    Uses official search API to bypass all scraping blocks.
    No more 401 Proxy errors or Malformed URL crashes.
    """
    all_reviews = []
    
    try:
        # 1. Resolve Company Name
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        search_query = place_id if place_id else (company.name if company else "Villa The Grand Buffet")

        logger.info(f"🚀 SerpApi Ingest Start: {search_query} (ID: {company_id})")

        # 2. Configure SerpApi Parameters
        # This searches for the business and grabs the local reviews directly
        params = {
            "engine": "google_maps_reviews",
            "type": "search",
            "q": search_query,
            "api_key": SERPAPI_KEY,
            "hl": "en",
            "gl": "pk"
        }

        # 3. Execute Search (Run in thread to keep FastAPI async)
        def run_search():
            search = GoogleSearch(params)
            return search.get_dict()

        results = await asyncio.to_thread(run_search)

        # 4. Check for Errors
        if "error" in results:
            logger.error(f"❌ SerpApi Error: {results['error']}")
            return []

        # 5. Extract Reviews
        raw_reviews = results.get("reviews", [])
        logger.info(f"✅ SerpApi found {len(raw_reviews)} reviews.")

        # 6. Map to your Model format
        for i, r in enumerate(raw_reviews[:limit]):
            all_reviews.append({
                "review_id": r.get("review_id", f"SERP-{company_id}-{i}"),
                "author_name": r.get("user", {}).get("name", "Google User"),
                "rating": int(r.get("rating", 5)),
                "text": r.get("snippet") or r.get("text") or "No review text provided.",
                "date": r.get("date"),
                "likes": r.get("likes", 0)
            })

    except Exception as e:
        logger.error(f"❌ SerpApi Scraper failed: {str(e)}", exc_info=True)

    logger.info(f"🏁 Finished: Captured {len(all_reviews)} reviews via SerpApi.")
    return all_reviews
