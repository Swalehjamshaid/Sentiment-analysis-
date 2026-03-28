# app/services/scraper.py

import os
import asyncio
import logging
from typing import List, Dict, Optional
from serpapi import GoogleSearch

logger = logging.getLogger("app.scraper")

SERP_API_KEY = os.getenv("SERP_API_KEY")


# =========================================================
# RUN BLOCKING SERPAPI IN THREAD (IMPORTANT FOR FASTAPI)
# =========================================================
async def run_serpapi(params: dict):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: GoogleSearch(params).get_dict()
    )


# =========================================================
# MAIN FETCH FUNCTION (ALIGNED WITH reviews.py)
# =========================================================
async def fetch_reviews(
    place_id: str,
    limit: int = 300,
    name: Optional[str] = None
) -> List[Dict]:

    """
    Production-ready Google Reviews scraper using SerpAPI.

    Flow:
    1. Resolve Place ID → CID (data_id)
    2. Fallback: Search by name if needed
    3. Fetch reviews using CID
    4. Return clean structured data
    """

    if not SERP_API_KEY:
        logger.error("❌ SERP_API_KEY is missing")
        return []

    if not place_id:
        logger.error("❌ place_id is required")
        return []

    target_name = name or "Business"

    try:
        logger.info(f"🚀 Scraping started for: {target_name}")

        # =====================================================
        # STEP 1: RESOLVE CID USING PLACE_ID
        # =====================================================
        cid = None

        try:
            params = {
                "engine": "google_maps",
                "place_id": place_id,
                "api_key": SERP_API_KEY,
                "no_cache": True
            }

            response = await run_serpapi(params)
            cid = response.get("place_results", {}).get("data_id")

        except Exception as e:
            logger.warning(f"⚠️ Place ID resolution failed: {e}")

        # =====================================================
        # STEP 2: FALLBACK USING NAME SEARCH
        # =====================================================
        if not cid:
            logger.warning(f"⚠️ Falling back to name search: {target_name}")

            try:
                params = {
                    "engine": "google_maps",
                    "q": target_name,
                    "api_key": SERP_API_KEY
                }

                response = await run_serpapi(params)

                # Try direct place_results
                cid = response.get("place_results", {}).get("data_id")

                # Fallback to first local result
                if not cid:
                    local = response.get("local_results", [])
                    if local:
                        cid = local[0].get("data_id")

            except Exception as e:
                logger.error(f"❌ Name fallback failed: {e}")

        # =====================================================
        # FAIL SAFE
        # =====================================================
        if not cid:
            logger.error(f"❌ CID not found for: {target_name}")
            return []

        logger.info(f"📍 CID resolved: {cid}")

        # =====================================================
        # STEP 3: FETCH REVIEWS
        # =====================================================
        params = {
            "engine": "google_maps_reviews",
            "data_id": cid,
            "api_key": SERP_API_KEY,
            "sort_by": "newest",
            "num": min(limit, 100)  # SerpAPI limit per request
        }

        response = await run_serpapi(params)
        raw_reviews = response.get("reviews", [])

        if not raw_reviews:
            logger.warning(f"⚠️ No reviews returned from API")
            return []

        # =====================================================
        # STEP 4: FORMAT DATA (MATCH reviews.py)
        # =====================================================
        final_results = []

        for r in raw_reviews:

            review_id = r.get("review_id") or r.get("id")
            if not review_id:
                continue

            final_results.append({
                "review_id": review_id,
                "author_name": r.get("user", {}).get("name", "Anonymous"),
                "rating": r.get("rating", 0),
                "text": r.get("snippet") or r.get("text") or "",
            })

        logger.info(f"✅ Fetched {len(final_results)} reviews for {target_name}")

        return final_results

    except Exception as e:
        logger.error(f"❌ Scraper crash: {str(e)}", exc_info=True)
        return []
