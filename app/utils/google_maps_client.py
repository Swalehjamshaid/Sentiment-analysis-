
import os
try:
    import googlemaps  # type: ignore
except Exception:
    googlemaps = None

_client = None

def _ensure_client():
    global _client
    if _client is None and googlemaps:
        key = os.getenv('GOOGLE_MAPS_API_KEY') or os.getenv('GOOGLE_API_KEY') or os.getenv('GOOGLE_PLACES_API_KEY')
        if key:
            try:
                _client = googlemaps.Client(key=key)
            except Exception:
                _client = None
    return _client

def get_api_key():
    return os.getenv('GOOGLE_MAPS_API_KEY') or os.getenv('GOOGLE_API_KEY') or ''

def geocode_address(address: str):
    c = _ensure_client()
    if not c:
        return None
    try:
        res = c.geocode(address)
        return res
    except Exception:
        return None

def get_distance(origin: str, destination: str):
    c = _ensure_client()
    if not c:
        return None
    try:
        res = c.distance_matrix(origins=[origin], destinations=[destination])
        return res
    except Exception:
        return None
