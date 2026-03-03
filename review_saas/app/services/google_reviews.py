# filename: app/services/google_reviews.py
import requests
from typing import Dict, Any, Optional, List
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
    response.raise_for_status()
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

def ingest_company_reviews(company_id: int, place_id: str) -> List[Dict[str, Any]]:
    """
    Fetch reviews for a company and return a list of review dicts.
    """
    place_data = fetch_place_details(place_id)
    if not place_data:
        return []

    reviews = place_data.get("reviews", [])
    # Here you can also add code to save reviews to DB if needed
    return reviews
