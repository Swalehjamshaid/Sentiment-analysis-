from typing import List, Dict
    from ..core.settings import settings

    async def fetch_reviews(place_id: str, max_count: int = 200) -> List[Dict]:
        # Stub: call Google Places API with settings.GOOGLE_API_KEY.
        # Return list of dicts with keys: id, text, rating, time, author_name, profile_photo_url
        return []