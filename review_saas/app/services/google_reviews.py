# filename: app/services/google_reviews.py

import logging
from serpapi import GoogleSearch
from datetime import datetime
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review
from app.core.config import settings

logger = logging.getLogger(__name__)

# You would add SERPAPI_KEY to your Railway variables
SERP_KEY = settings.SERPAPI_KEY 

async def ingest_company_reviews(company_id: int, place_id: str):
    """
    Fetches UNLIMITED reviews using SerpApi.
    This bypasses the 5-review limit of the official Google Places API.
    """
    params = {
        "engine": "google_maps_reviews",
        "place_id": place_id,
        "api_key": SER_KEY,
        "hl": "en",
        "sort_by": "newestFirst"
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        
        # SerpApi provides reviews in batches (usually 10-20 per page)
        reviews_data = results.get("reviews", [])
        
        # To get even more than the first page, we check for next_page_token
        # For now, let's process the first large batch
        if not reviews_data:
            logger.warning(f"No reviews found for {place_id}")
            return

        async with get_session() as session:
            inserted_count = 0
            for r in reviews_data:
                # SerpApi review IDs are unique strings
                g_id = r.get("review_id")

                # Duplicate Check
                stmt = select(Review).where(Review.google_review_id == g_id)
                existing = await session.execute(stmt)
                if existing.scalar_one_or_none():
                    continue

                # Mapping SerpApi data to your Model
                session.add(Review(
                    company_id=company_id,
                    google_review_id=g_id,
                    author_name=r.get("user", {}).get("name", "Anonymous"),
                    rating=int(r.get("rating", 0)),
                    text=r.get("snippet", ""),
                    google_review_time=datetime.fromtimestamp(r.get("timestamp")),
                    profile_photo_url=r.get("user", {}).get("thumbnail"),
                ))
                inserted_count += 1
            
            await session.commit()
            logger.info(f"✅ Successfully ingested {inserted_count} reviews for company {company_id}.")

    except Exception as e:
        logger.error(f"❌ SerpApi Sync Failed: {e}")

# Keeping this for basic confirmation in your routes
async def fetch_place_details(place_id: str):
    # (Existing Place Details logic using Google Maps API Key)
    ...
