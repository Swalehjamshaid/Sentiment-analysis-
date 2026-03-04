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
    """
    Fetch basic place details from Google Places API.
    Can be imported by app/routes/reviews.py
    """
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
            logger.warning("Business API failed, falling back to Places API.")
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
# Main Ingestion Function
# ---------------------------------------------------------
async def ingest_company_reviews(company_id: int, place_id: str):
    """
    1. Fetch reviews from Google APIs.
    2. Map data to the exact schema in app/core/models.py.
    3. Commit changes to the database.
    """
    logger.info(f"Starting review ingestion for company_id={company_id}")

    try:
        # Fetch reviews (Try Business API, then fallback to Places API)
        reviews = await _fetch_reviews_from_business_api(place_id)
        if not reviews:
            logger.info("Using Google Places API fallback.")
            reviews = _fetch_reviews_from_places_api(place_id)

        if not reviews:
            logger.info("No reviews found from either API.")
            return

        async with get_session() as session:
            # We use a transaction block to ensure data integrity
            async with session.begin():
                for r in reviews:
                    # EXTRACT DATA
                    author = r.get("reviewer", {}).get("displayName") if "reviewer" in r else r.get("author_name")
                    rating = r.get("starRating") if "starRating" in r else r.get("rating")
                    text = r.get("comment") if "comment" in r else r.get("text")
                    photo = r.get("reviewer", {}).get("profilePhotoUrl") if "reviewer" in r else r.get("profile_photo_url")

                    # FORMAT TIME (Required by model: google_review_time)
                    g_time = None
                    if "createTime" in r:
                        # Business API format
                        g_time = datetime.fromisoformat(r["createTime"].replace("Z", "+00:00"))
                    elif "time" in r:
                        # Places API format (Unix timestamp)
                        g_time = datetime.fromtimestamp(r["time"], tz=timezone.utc)

                    # GENERATE UNIQUE ID (Required by model: google_review_id)
                    g_id = r.get("reviewId") or f"{place_id}_{r.get('time', 0)}_{author}"

                    # PREVENT DUPLICATES
                    existing = await session.execute(
                        select(Review).where(Review.google_review_id == g_id)
                    )
                    if existing.scalar_one_or_none():
                        continue

                    # CREATE MODEL INSTANCE (Using exact names from models.py)
                    new_review = Review(
                        company_id=company_id,
                        google_review_id=g_id,
                        author_name=author,
                        rating=int(rating) if rating else 0,
                        text=text,
                        google_review_time=g_time,
                        profile_photo_url=photo,
                    )
                    session.add(new_review)

                # The transaction block automatically COMMITS all changes here 💾
        
        logger.info(f"✅ Successfully ingested reviews for company {company_id}")

    except Exception as e:
        logger.error(f"❌ Review ingestion failed: {e}")
