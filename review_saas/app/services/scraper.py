import os
import asyncio
import logging
from typing import List, Dict, Optional
from serpapi import GoogleSearch
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger("app.scraper")
logger.setLevel(logging.INFO)

SERP_API_KEY = os.getenv("SERP_API_KEY")
if not SERP_API_KEY:
    logger.warning("⚠️ SERP_API_KEY not set. Scraper may fail.")

analyzer = SentimentIntensityAnalyzer()


async def fetch_reviews(place_id: Optional[str] = None, name: Optional[str] = None, limit: int = 300) -> List[Dict]:
    """
    Robust async scraper for Google reviews using SerpAPI.
    - Tries CID resolution first
    - Falls back to search by name if CID fails
    - Handles 0 reviews gracefully
    """
    if not place_id and not name:
        logger.error("❌ fetch_reviews called without place_id or name.")
        return []

    target_name = name or "Restaurant"
    target_id = place_id

    # Optional hardcoded map for legacy places
    id_map = {
        "ChIJDVYKpFEEGTkRp_XASXZ21Tc": "Salt'n Pepper Village Lahore",
        "ChIJe2LWbaIIGTkRZhr_Fbyvkvs": "Gloria Jeans Coffees DHA Phase 5 Lahore",
        "ChIJ8S6kk9YJGtkRWK6XHzCKsrA": "McDonald's Lahore"
    }
    if not name and place_id in id_map:
        target_name = id_map[place_id]

    logger.info(f"🚀 [Scraper] Starting ingestion: {target_name} ({target_id})")

    # Async helper to run blocking SerpAPI calls
    async def serpapi_call(params: dict) -> dict:
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, lambda: GoogleSearch(params).get_dict())
        except Exception as e:
            logger.error(f"❌ SerpAPI call failed: {e}")
            return {}

    try:
        # 1️⃣ Resolve CID if place_id provided
        data_id = None
        if target_id:
            resolver_params = {
                "engine": "google_maps",
                "place_id": target_id,
                "api_key": SERP_API_KEY,
                "no_cache": True
            }
            res = await serpapi_call(resolver_params)
            data_id = res.get("place_results", {}).get("data_id")

        # 2️⃣ Fallback: search by name
        if not data_id:
            logger.warning(f"⚠️ CID not found. Searching by name: {target_name}")
            search_params = {
                "engine": "google_maps",
                "q": target_name,
                "api_key": SERP_API_KEY,
                "no_cache": True
            }
            search_res = await serpapi_call(search_params)
            local_results = search_res.get("local_results") or []
            place_results = search_res.get("place_results") or (local_results[0] if local_results else {})
            data_id = place_results.get("data_id")

        if not data_id:
            logger.error(f"❌ Failed to resolve CID for {target_name}. Returning empty list.")
            return []

        # 3️⃣ Fetch reviews
        logger.info(f"📍 CID Resolved: {data_id}. Fetching reviews...")
        reviews_params = {
            "engine": "google_maps_reviews",
            "data_id": data_id,
            "api_key": SERP_API_KEY,
            "num": limit,
            "no_cache": True,
            "sort_by": "newest"
        }
        review_res = await serpapi_call(reviews_params)
        raw_reviews = review_res.get("reviews", [])

        if not raw_reviews:
            logger.warning(f"⚠️ 0 reviews found for {target_name} (CID: {data_id})")
            return []

        # 4️⃣ Map reviews
        final_reviews = []
        for r in raw_reviews[:limit]:
            text = r.get("snippet") or r.get("text") or "No comment"
            sentiment = analyzer.polarity_scores(text)
            final_reviews.append({
                "review_id": r.get("review_id"),
                "author_name": r.get("user", {}).get("name", "Anonymous"),
                "rating": r.get("rating", 0),
                "text": text,
                "sentiment": "Positive" if sentiment["compound"] >= 0.05 else "Negative"
            })

        logger.info(f"✅ Fetched {len(final_reviews)} reviews for {target_name}")
        return final_reviews

    except Exception as e:
        logger.error(f"❌ Scraper exception for {target_name}: {e}", exc_info=True)
        return []
