import os
import asyncio
from typing import List, Optional, Dict
from serpapi import GoogleSearch
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger("app.scraper")

# Ensure you have SERP_API_KEY in your environment
SERP_API_KEY = os.getenv("SERP_API_KEY")

if not SERP_API_KEY:
    raise RuntimeError("SERP_API_KEY environment variable not set!")


async def fetch_reviews(
    place_id: Optional[str] = None,
    name: Optional[str] = None,
    limit: int = 50,
    session: Optional[AsyncSession] = None,
    company_id: Optional[int] = None,  # NEW: accept company_id
) -> List[Dict]:
    """
    Fetch Google reviews using SerpApi.
    Returns a list of review dicts ready for database ingestion.
    """

    if not place_id and not name:
        raise ValueError("Must provide either place_id or name to fetch reviews.")

    logger.info(f"Fetching reviews for {name or place_id} (limit={limit})")

    # SerpApi parameters
    params = {
        "engine": "google_reviews",
        "google_place_id": place_id,  # Google Place ID
        "api_key": SERP_API_KEY,
        "hl": "en",
    }

    # Run search using SerpApi
    try:
        search = GoogleSearch(params)
        results = search.get_dict()
    except Exception as e:
        logger.error(f"SerpApi fetch failed: {str(e)}")
        return []

    reviews = results.get("reviews", [])
    if not reviews:
        logger.info("No reviews found from SerpApi")
        return []

    # Limit reviews
    reviews = reviews[:limit]

    # Map SerpApi review structure to our DB structure
    formatted_reviews = []
    for rev in reviews:
        formatted_reviews.append({
            "company_id": company_id,
            "review_id": rev.get("review_id") or rev.get("user") + str(rev.get("time")),
            "author_name": rev.get("user_name"),
            "rating": rev.get("rating"),
            "text": rev.get("snippet"),
            "google_review_time": rev.get("time"),
            "source_platform": "Google",
        })

    logger.info(f"Fetched {len(formatted_reviews)} reviews for {name or place_id}")
    return formatted_reviews
