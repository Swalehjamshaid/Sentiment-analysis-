# filename: app/app/services/google_api.py
import logging
from typing import Optional, Dict, Any
from app.core.config import get_settings

logger = logging.getLogger('googlemaps.client')
_client = None

try:
    import googlemaps
except Exception:
    googlemaps = None

def _ensure_client():
    global _client
    if _client is None and googlemaps is not None:
        s = get_settings()
        key = s.google_maps_api_key or s.google_places_api_key
        if key:
            _client = googlemaps.Client(key=key)
            logger.info('API queries_quota: 60')
    return _client

def get_place_details(place_id: str) -> Optional[Dict[str, Any]]:
    client = _ensure_client()
    if not client:
        return None
    try:
        resp = client.place(place_id=place_id)
        r = resp.get('result') or {}
        comps = {c['types'][0]: c for c in r.get('address_components', []) if c.get('types')}
        return {
            'name': r.get('name'),
            'formatted_address': r.get('formatted_address'),
            'formatted_phone_number': r.get('formatted_phone_number'),
            'website': r.get('website'),
            'url': r.get('url'),
            'administrative_area_level_1': (comps.get('administrative_area_level_1') or {}).get('short_name'),
            'postal_code': (comps.get('postal_code') or {}).get('short_name'),
            'country': (comps.get('country') or {}).get('short_name'),
            'rating': r.get('rating'),
            'user_ratings_total': r.get('user_ratings_total'),
            'types': r.get('types'),
        }
    except Exception as ex:
        logging.getLogger('review_saas.main').warning(f'get_place_details error: {ex}')
        return None
