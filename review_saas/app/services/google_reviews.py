
# filename: app/services/google_reviews.py
from __future__ import annotations
from typing import List, Dict
from googlemaps import Client as GoogleMaps
from ..core.settings import settings


def fetch_place_details(place_id: str) -> Dict:
    if not settings.GOOGLE_PLACES_API_KEY:
        return {}
    gmaps = GoogleMaps(key=settings.GOOGLE_PLACES_API_KEY)
    return gmaps.place(place_id=place_id)


def fetch_reviews(place_id: str, page_size: int = 100) -> List[Dict]:
    # NOTE: Google Places API has limits; here we return an empty list as a placeholder.
    # Integrate with Places API (Place Details) as needed and map fields to our schema.
    details = fetch_place_details(place_id) or {}
    reviews = details.get('result', {}).get('reviews', [])
    out = []
    for r in reviews[:page_size]:
        out.append({
            'external_id': r.get('author_url') or r.get('time'),
            'text': r.get('text'),
            'rating': r.get('rating'),
            'review_date': r.get('time'),
            'reviewer_name': r.get('author_name'),
            'reviewer_avatar': r.get('profile_photo_url'),
        })
    return out
