# filename: app/services/google_reviews.py

import logging
import httpx
from datetime import datetime, timezone
from sqlalchemy import select

from app.core.db import get_session
from app.core.models import Review
from app.core.config import settings

logger = logging.getLogger(__name__)

async def fetch_place_details(place_id: str):
    """
    Fetch basic business details using the Business API.
    Aligned with Company model fields.
    """
    token = getattr(settings, "GOOGLE_BUSINESS_ACCESS_TOKEN", None)
    if not token:
        logger.error("GOOGLE_BUSINESS_ACCESS_TOKEN missing")
        return {}

    url = f"https://mybusiness.googleapis.com/v4/accounts/-/locations/{place_id}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            return {}
        
        data = response.json()
        return {
            "name": data.get("locationName"),
            "address": data.get("address", {}).get("addressLines", [""])[0] if data.get("address") else ""
        }

async def _fetch_reviews_from_business_api(place_id: str):
    token = getattr(settings, "GOOGLE_BUSINESS_ACCESS_TOKEN", None)
    if not token: return None
    
    url = f"https://mybusiness.googleapis.com/v4/accounts/-/locations/{place_id}/reviews"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(url, headers=headers)
        if res.status_code != 200:
            logger.error(f"Business API error: {res.status_code} - {res.text}")
            return None
        return res.json().get("reviews", [])

async def ingest_company_reviews(company_id: int, place_id: str):
    """
    Ingests reviews and aligns them with the Review model schema.
    Matches google_review_id, rating, and google_review_time constraints.
    """
    logger.info(f"Starting FULL ingestion for company_id={company_id}")
    try:
        reviews_data = await _fetch_reviews_from_business_api(place_id)
        if not reviews_data:
            logger.warning("No reviews found for this location.")
            return

        async with get_session() as session:
            # session.begin() ensures an atomic transaction (COMMIT/ROLLBACK)
            async with session.begin():
                for r in reviews_data:
                    # 1. Handle google_review_id (Required: nullable=False)
                    g_id = r.get("reviewId")
                    if not g_id:
                        continue

                    # 2. Handle google_review_time (Required: nullable=False)
                    g_time = None
                    if "createTime" in r:
                        g_time = datetime.fromisoformat(r["createTime"].replace("Z", "+00:00"))
                    else:
                        g_time = datetime.now(timezone.utc)

                    # 3. Check for duplicates using the unique constraint field
                    exists = await session.execute(
                        select(Review).where(Review.google_review_id == g_id)
                    )
                    if exists.scalar_one_or_none():
                        continue

                    # 4. Extract and Clean Rating (Required: nullable=False)
                    raw_rating = r.get("starRating", "STAR_RATING_UNSPECIFIED")
                    clean_rating = 0
                    if "STAR_RATING_" in raw_rating:
                        try:
                            clean_rating = int(raw_rating.replace("STAR_RATING_", ""))
                        except ValueError:
                            clean_rating = 0

                    # 5. Populate the Review model instance
                    session.add(Review(
                        company_id=company_id,
                        google_review_id=g_id,
                        author_name=r.get("reviewer", {}).get("displayName"),
                        profile_photo_url=r.get("reviewer", {}).get("profilePhotoUrl"),
                        rating=clean_rating,
                        text=r.get("comment") or "",
                        google_review_time=g_time,
                        language=r.get("languageCode")
                    ))
                    
        logger.info(f"✅ Full sync complete. Processed {len(reviews_data)} reviews.")
    except Exception as e:
        logger.error(f"❌ Ingestion failed: {e}")
