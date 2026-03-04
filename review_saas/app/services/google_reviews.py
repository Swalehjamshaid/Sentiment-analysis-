# filename: app/services/google_reviews.py
import logging
import googlemaps
import httpx
from datetime import datetime
from sqlalchemy import select

from app.core.db import get_session
from app.core.models import Review
from app.core.config import settings

logger = logging.getLogger(__name__)

def _get_places_client():
    if not settings.GOOGLE_PLACES_API_KEY:
        return None
    return googlemaps.Client(key=settings.GOOGLE_PLACES_API_KEY)

async def _fetch_reviews_from_business_api(place_id: str):
    access_token = getattr(settings, "GOOGLE_BUSINESS_ACCESS_TOKEN", None)
    if not access_token:
        logger.warning("No Google Business OAuth token found.")
        return []
    url = f"https://mybusiness.googleapis.com/v4/accounts/-/locations/{place_id}/reviews"
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            logger.warning("Business API failed, falling back to Places API.")
            return []
        return response.json().get("reviews", [])

def _fetch_reviews_from_places_api(place_id: str):
    client = _get_places_client()
    if not client:
        return []
    result = client.place(place_id=place_id, fields=["reviews"])
    return result.get("result", {}).get("reviews", [])

async def ingest_company_reviews(company_id: int, place_id: str):
    logger.info(f"Starting review ingestion for company_id={company_id}")

    try:
        # 1️⃣ Try Business API
        reviews = await _fetch_reviews_from_business_api(place_id)
        # 2️⃣ Fallback to Places API
        if not reviews:
            logger.info("Using Google Places API fallback.")
            reviews = _fetch_reviews_from_places_api(place_id)
        if not reviews:
            logger.info("No reviews found for this company.")
            return

        async with get_session() as session:
            for r in reviews:
                # Extract unique review ID
                google_review_id = r.get("reviewId") or r.get("author_url") or r.get("author_name")
                if not google_review_id:
                    continue  # skip if no unique ID

                # Extract other fields
                author = r.get("reviewer", {}).get("displayName") if "reviewer" in r else r.get("author_name")
                rating = r.get("starRating") if "starRating" in r else r.get("rating")
                text = r.get("comment") if "comment" in r else r.get("text")
                profile_photo = r.get("reviewer", {}).get("profilePhotoUrl") if "reviewer" in r else r.get("profile_photo_url")

                # Correct timestamp field
                google_review_time = None
                if "createTime" in r:
                    google_review_time = datetime.fromisoformat(r["createTime"].replace("Z", "+00:00"))
                elif "time" in r:
                    google_review_time = datetime.utcfromtimestamp(r["time"])

                # Prevent duplicates using UniqueConstraint
                existing = await session.execute(
                    select(Review).where(
                        Review.company_id == company_id,
                        Review.google_review_id == google_review_id
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                # Create Review object
                new_review = Review(
                    company_id=company_id,
                    google_review_id=google_review_id,
                    author_name=author,
                    rating=int(rating) if rating else 0,
                    text=text,
                    google_review_time=google_review_time or datetime.utcnow(),
                    profile_photo_url=profile_photo,
                )
                session.add(new_review)

            await session.commit()
        logger.info("Review ingestion completed successfully.")

    except Exception as e:
        logger.error(f"Review ingestion failed: {e}")
