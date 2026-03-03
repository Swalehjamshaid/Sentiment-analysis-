from __future__ import annotations
from typing import List, Dict
import requests
from app.core.config import settings

GOOGLE_PLACES_API_KEY = settings.GOOGLE_PLACES_API_KEY

def fetch_place_details(place_id: str) -> Dict:
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,rating,reviews,formatted_address,formatted_phone_number,website,types,opening_hours",
        "key": GOOGLE_PLACES_API_KEY
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    return data.get("result", {})

def ingest_company_reviews(company_id: int, place_id: str) -> List[Dict]:
    details = fetch_place_details(place_id)
    reviews = details.get("reviews", [])
    out = []
    for r in reviews:
        out.append({
            "author_name": r.get("author_name"),
            "rating": r.get("rating"),
            "text": r.get("text"),
            "review_time": r.get("relative_time_description")
        })
    return out
