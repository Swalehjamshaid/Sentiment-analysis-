import os, asyncio
    import httpx
    from ..core.config import settings

    async def validate_place_id(place_id: str) -> bool:
        if not place_id:
            return True
        if not settings.GOOGLE_API_KEY:
            return True  # allow in dev
        url = 'https://maps.googleapis.com/maps/api/place/details/json'
        params = {'place_id': place_id, 'key': settings.GOOGLE_API_KEY, 'fields': 'place_id,status'}
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params)
            j = r.json()
            return j.get('status') == 'OK' and j.get('result', {}).get('place_id') == place_id

    async def fetch_reviews(place_id: str, page_size: int = 100) -> list[dict]:
        if not settings.GOOGLE_API_KEY:
            # demo payload
            return [{"review_id": f"demo-{i}", "text": f"Sample review {i}", "rating": 5, "time": "", "author_name": "Demo"} for i in range(min(page_size, 50))]
        # TODO: real Places Reviews API integration (pagination + backoff)
        return []