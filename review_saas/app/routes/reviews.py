from fastapi import APIRouter, Depends
    from ..services.google_places import fetch_reviews

    router = APIRouter(prefix="/reviews", tags=["reviews"])

    @router.post("/fetch/{place_id}")
    async def fetch(place_id: str):
        reviews = await fetch_reviews(place_id)
        return {"fetched": len(reviews)}