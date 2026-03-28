# app/services/scraper.py
import os
import asyncio
import logging
from typing import List, Dict, Optional
from serpapi import GoogleSearch

logger = logging.getLogger("app.scraper")

# Make sure SERP_API_KEY is set in your environment
SERP_API_KEY = os.getenv("SERP_API_KEY")

# --------------------------- Fetch Reviews ---------------------------
async def fetch_reviews(place_id: str, limit: int = 100) -> List[Dict[str, Optional[str]]]:
    """
    Fetch Google reviews using SerpAPI for a given place_id.
    Returns a list of dictionaries compatible with your Review DB model:
      - review_id
      - author_name
      - rating
      - text
      - time (optional, UTC timestamp)
    """
    reviews: List[Dict[str, Optional[str]]] = []

    if not place_id:
        logger.warning("No Place ID provided to fetch_reviews")
        return reviews

    params = {
        "engine": "google_reviews",
        "google_place_id": place_id,
        "api_key": SERP_API_KEY,
        "hl": "en",
        "num": 100  # SerpAPI max reviews per request
    }

    try:
        # SerpAPI is blocking; run in executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: GoogleSearch(params).get_dict())

        fetched_reviews = response.get("reviews", [])
        if not fetched_reviews:
            logger.info(f"No reviews found for place_id: {place_id}")
            return reviews

        # Limit the reviews as requested
        for r in fetched_reviews[:limit]:
            reviews.append({
                "review_id": r.get("review_id") or r.get("id"),  # fallback keys
                "author_name": r.get("user_name"),
                "rating": r.get("rating"),
                "text": r.get("text"),
                "time": r.get("time")  # optional, can be converted to datetime in ingestion
            })

        logger.info(f"Fetched {len(reviews)} reviews from SerpAPI for place_id: {place_id}")

    except Exception as e:
        logger.error(f"Error fetching reviews for {place_id}: {str(e)}", exc_info=True)

    return reviews
