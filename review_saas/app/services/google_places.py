
import httpx, backoff
from ..config import GOOGLE_API_KEY, REVIEW_FETCH_MAX

BASE = 'https://maps.googleapis.com/maps/api/place'

class GooglePlacesError(Exception):
    pass

@backoff.on_exception(backoff.expo, (httpx.HTTPError,), max_tries=5)
async def validate_place_id(place_id: str):
    url = f"{BASE}/details/json"
    params = {"place_id": place_id, "fields": "place_id,name,geometry", "key": GOOGLE_API_KEY}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        if data.get('status') != 'OK':
            raise GooglePlacesError(data.get('status', 'ERROR'))
        return data['result']

@backoff.on_exception(backoff.expo, (httpx.HTTPError,), max_tries=5)
async def fetch_reviews(place_id: str, page_token: str | None = None):
    # Google Places API returns up to ~5 most helpful reviews in details endpoint.
    # For more, you might need Places API Advanced or scraping (not recommended).
    url = f"{BASE}/details/json"
    params = {"place_id": place_id, "fields": "reviews,name,place_id", "key": GOOGLE_API_KEY}
    if page_token:
        params['page_token'] = page_token
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        if data.get('status') not in ('OK', 'ZERO_RESULTS'):
            raise GooglePlacesError(data.get('status', 'ERROR'))
        reviews = data.get('result', {}).get('reviews', [])
        # Normalize to common schema
        normalized = []
        for rv in reviews[:REVIEW_FETCH_MAX]:
            normalized.append({
                'external_id': str(rv.get('time')),
                'text': rv.get('text', ''),
                'rating': rv.get('rating'),
                'review_datetime': rv.get('time'),
                'reviewer_name': rv.get('author_name', 'Anonymous'),
                'reviewer_pic_url': rv.get('profile_photo_url')
            })
        return normalized, None
