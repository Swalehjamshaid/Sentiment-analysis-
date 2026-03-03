import requests
from typing import Dict, Any, Optional
from app.core.config import settings


def fetch_place_details(place_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch place details and reviews using Google Places API.
    """

    if not settings.GOOGLE_PLACES_API_KEY:
        raise ValueError("GOOGLE_PLACES_API_KEY is not configured")

    url = "https://maps.googleapis.com/maps/api/place/details/json"

    params = {
        "place_id": place_id,
        "fields": "name,rating,user_ratings_total,reviews",
        "key": settings.GOOGLE_PLACES_API_KEY,
    }

    response = requests.get(url, params=params, timeout=10)

    if response.status_code != 200:
        raise Exception(f"Google API HTTP error: {response.status_code}")

    data = response.json()

    if data.get("status") != "OK":
        raise Exception(f"Google API error: {data.get('status')}")

    result = data.get("result", {})

    return {
        "name": result.get("name"),
        "rating": result.get("rating"),
        "total_reviews": result.get("user_ratings_total"),
        "reviews": result.get("reviews", []),
    }
