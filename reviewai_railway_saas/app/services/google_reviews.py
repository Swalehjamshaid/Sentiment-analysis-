from __future__ import annotations
from typing import List, Dict, Any
import requests
from datetime import datetime

from ..database import settings

# Utilities to fetch reviews from Google.
# - Places API typically returns up to 5 public reviews.
# - For complete review management (list & reply), use Google Business Profile APIs with OAuth and location ownership.

GOOGLE_DETAILS_URL = 'https://maps.googleapis.com/maps/api/place/details/json'

def fetch_places_reviews(place_id: str) -> List[Dict[str, Any]]:
    """Fetch public reviews via Places Details (limited reviews)."""
    params = {
        'place_id': place_id,
        'fields': 'name,reviews,rating,user_ratings_total',
        'key': settings.GOOGLE_MAPS_API_KEY,
    }
    r = requests.get(GOOGLE_DETAILS_URL, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    reviews = data.get('result', {}).get('reviews', [])
    out = []
    for rv in reviews:
        out.append({
            'review_text': rv.get('text'),
            'star_rating': rv.get('rating'),
            'review_date': datetime.fromtimestamp(rv.get('time', 0)),
            'reviewer_name': rv.get('author_name'),
        })
    return out

def fetch_gbp_reviews_stub(location_name: str) -> List[Dict[str, Any]]:
    # Placeholder to illustrate GBP flow (requires OAuth and ownership).
    return []
