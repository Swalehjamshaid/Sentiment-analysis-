import logging
import googlemaps
import httpx
from datetime import datetime, timezone
from sqlalchemy import select

from app.core.db import get_session
from app.core.models import Review
from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# Google Places Client
# ---------------------------------------------------------
def _get_places_client():
    if not settings.GOOGLE_PLACES_API_KEY:
        return None
    return googlemaps.Client(key=settings.GOOGLE_PLACES_API_KEY)

# ---------------------------------------------------------
# REQUIRED FUNCTION (Top-level for import)
# ---------------------------------------------------------
def fetch_place_details(place_id: str):
    client = _get_places_client()
    if not client:
        raise Exception("GOOGLE_PLACES_API_KEY not configured")

    result = client.place(
        place_id=place_id,
        fields=["name", "rating", "user_ratings_total", "formatted_address"]
    )
    return result.get("result", {})

# ---------------------------------------------------------
# Google Business API (OAuth Required)
# ---------------------------------------------------------
async def _fetch_reviews_from_business_api(place_id: str):
    access_token = getattr(settings, "GOOGLE_BUSINESS_ACCESS_TOKEN", None)
    if not access_token:
        logger.warning("No Google Business OAuth token found.")
        return None

    url = f"https://mybusiness.googleapis.com/v4/accounts/-/locations/{place_id}/reviews"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            return None
        return response.json().get("reviews", [])

# ---------------------------------------------------------
# Google Places API (Fallback - Max 5 Reviews)
# ---------------------------------------------------------
def _fetch_reviews_from_places_api(place_id: str):
    client = _get_places_client()
    if not client:
        return []

    result = client.place(
        place_id=place_id,
        fields=["reviews"]
    )
    return result.get("result", {}).get("reviews", [])

# ---------------------------------------------------------
# Main Ingestion Function (The Fix)
# ---------------------------------------------------------
async def ingest_company_reviews(company_id: int, place_id: str):
    """
    Ensures data matches Review model fields: google_review_id, google_review_time, etc.
    """
    logger.info(f"Starting review ingestion for company_id={company_id}")

    try:
        # 1. Fetch data
        reviews_data = await _fetch_reviews_from_business_api(place_id)
        if not reviews_data:
            reviews_data = _fetch_reviews_from_places_api(place_id)

        if not reviews_data:
            logger.info("No reviews found from Google APIs.")
            return

        async with get_session() as session:
            # 2. Start explicit transaction
            async with session.begin():
                for r in reviews_data:
                    # Map unique ID (Required by model: google_review_id)
                    g_id = r.get("reviewId") or f"{place_id}_{r.get('time', 0)}_{r.get('author_name')}"

                    # Map and format time (Required by model: google_review_time)
                    g_time = None
                    if "createTime" in r:
                        g_time = datetime.fromisoformat(r["createTime"].replace("Z", "+00:00"))
                    elif "time" in r:
                        g_time = datetime.fromtimestamp(r["time"], tz=timezone.utc)
                    else:
                        g_time = datetime.now(timezone.utc)

                    # 3. Prevent duplicate crashes (Check against the DB)
                    existing = await session.execute(
                        select(Review).where(Review.google_review_id == g_id)
                    )
                    if existing.scalar_one_or_none():
                        continue

                    # 4. Create Review using EXACT model names from your models.py
                    new_review = Review(
                        company_id=company_id,
                        google_review_id=g_id,       # Required
                        author_name=r.get("author_name") or r.get("reviewer", {}).get("displayName"),
                        rating=int(r.get("rating") or r.get("starRating") or 0), # Required
                        text=r.get("text") or r.get("comment") or "",
                        google_review_time=g_time,   # Required
                        profile_photo_url=r.get("profile_photo_url") or r.get("reviewer", {}).get("profilePhotoUrl"),
                    )
                    session.add(new_review)

                # The 'async with session.begin()' automatically COMMITS here 💾
        
        logger.info("✅ Review ingestion completed successfully.")

    except Exception as e:
        logger.error(f"❌ Review ingestion failed: {e}")
