# filename: app/services/scraper.py

import aiohttp
import asyncio
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Make sure to set your Google Places API key as an environment variable
import os
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise RuntimeError("GOOGLE_API_KEY environment variable is not set!")

BASE_URL = "https://maps.googleapis.com/maps/api/place/details/json"


async def fetch_google_place_details(place_id: str) -> Dict[str, Any]:
    """
    Fetch the full details of a place from Google Places API.
    Returns the JSON response.
    """
    params = {
        "place_id": place_id,
        "key": GOOGLE_API_KEY,
        "fields": "name,rating,user_ratings_total,reviews"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(BASE_URL, params=params) as resp:
            if resp.status != 200:
                logger.error(f"Google API returned {resp.status} for place_id {place_id}")
                raise Exception(f"Google API error {resp.status}")
            data = await resp.json()
            if data.get("status") != "OK":
                logger.error(f"Google API error: {data.get('status')} for place_id {place_id}")
                raise Exception(f"Google API error: {data.get('status')}")
            return data.get("result", {})


async def fetch_google_reviews(place_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetch reviews for a Google Place.
    """
    result = await fetch_google_place_details(place_id)
    reviews = result.get("reviews", [])
    # Limit the number of reviews returned
    return reviews[:limit]


async def fetch_google_rating(place_id: str) -> Dict[str, Any]:
    """
    Fetch basic rating info for a Google Place.
    """
    result = await fetch_google_place_details(place_id)
    return {
        "name": result.get("name"),
        "rating": result.get("rating"),
        "user_ratings_total": result.get("user_ratings_total")
    }


# Example test function (for local testing)
if __name__ == "__main__":
    import asyncio
    PLACE_ID = "ChIJ8S6kk9YJGTkRWK6XHzCKSrA"  # McDonald's example
    
    async def test():
        rating = await fetch_google_rating(PLACE_ID)
        reviews = await fetch_google_reviews(PLACE_ID, limit=5)
        print("Rating info:", rating)
        print("Sample reviews:", reviews)
    
    asyncio.run(test())
