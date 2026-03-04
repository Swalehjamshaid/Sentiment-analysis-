# filename: app/services/google_reviews.py

import logging
import httpx
from datetime import datetime, timezone
from sqlalchemy import select

from app.core.db import get_session
from app.core.models import Review
from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# RESTORED: fetch_place_details (Business API Version)
# ---------------------------------------------------------
async def fetch_place_details(place_id: str):
    """
    Fetch basic business details using the Business API.
    Required by routes/reviews.py to prevent ImportError.
    """
    access_token = getattr(settings, "GOOGLE_BUSINESS_ACCESS_TOKEN", None)
    if not access_token:
        logger.error("GOOGLE_BUSINESS_ACCESS_TOKEN not configured")
        return {}

    url = f"https://mybusiness.googleapis.com/v4/accounts/-/locations/{place_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            logger.error(f"Failed to fetch place details: {response.text}")
            return {}
        
        data = response.json()
        return {
            "name": data.get("locationName"),
            "formatted_address": data.get("address", {}).get("addressLines", [""])[0] if data.get("address") else ""
        }

# ---------------------------------------------------------
# Google Business API (Strict Ingestion)
# ---------------------------------------------------------
async def _fetch_reviews_from_business_api(place_id: str):
    access_token = getattr(settings, "GOOGLE_BUSINESS_ACCESS_TOKEN", None)
    if not access_token:
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
# Main Ingestion Function
# ---------------------------------------------------------
async def ingest_company_reviews(company_id: int, place_id: str):
    logger.info(f"Starting FULL review ingestion for company_id={company_id}")

    try:
        reviews_data = await _fetch_reviews_from_business_api(place_id)
        if not reviews_data:
            return

        async with get_session() as session:
            async with session.begin():
                for r in reviews_data:
                    g_id = r.get("reviewId")
                    g_time = datetime.fromisoformat(r["createTime"].replace("Z", "+00:00")) if "createTime" in r else datetime.now(timezone.utc)

                    existing = await session.execute(select(Review).where(Review.google_review_id == g_id))
                    if existing.scalar_one_or_none():
                        continue

                    new_review = Review(
                        company_id=company_id,
                        google_review_id=g_id,
                        author_name=r.get("reviewer", {}).get("displayName"),
                        rating=int(r.get("starRating", 0).replace("STAR_RATING_", "")) if "starRating" in r else 0,
                        text=r.get("comment") or "",
                        google_review_time=g_time,
                        profile_photo_url=r.get("reviewer", {}).get("profilePhotoUrl"),
                    )
                    session.add(new_review)
        
        logger.info(f"✅ Full ingestion completed. Processed {len(reviews_data)} reviews.")

    except Exception as e:
        logger.error(f"❌ Review ingestion failed: {e}")
