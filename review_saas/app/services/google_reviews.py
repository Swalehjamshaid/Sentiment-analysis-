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
# Google Business API (Strict Ingestion)
# ---------------------------------------------------------
async def _fetch_reviews_from_business_api(place_id: str):
    """
    Fetches full review history using OAuth2 Token.
    """
    access_token = getattr(settings, "GOOGLE_BUSINESS_ACCESS_TOKEN", None)
    if not access_token:
        logger.error("❌ CRITICAL: GOOGLE_BUSINESS_ACCESS_TOKEN is missing in settings.")
        return None

    # Note: place_id here must be the 'location resource name' for Business API
    url = f"https://mybusiness.googleapis.com/v4/accounts/-/locations/{place_id}/reviews"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 401:
                logger.error("❌ Business API Error: Unauthorized. Token may be expired.")
                return None
            if response.status_code != 200:
                logger.error(f"❌ Business API Error {response.status_code}: {response.text}")
                return None
            
            return response.json().get("reviews", [])
        except Exception as e:
            logger.error(f"❌ Connection to Business API failed: {e}")
            return None

# ---------------------------------------------------------
# Main Ingestion Function
# ---------------------------------------------------------
async def ingest_company_reviews(company_id: int, place_id: str):
    """
    Strictly uses Google Business API to bypass the 5-review limit.
    Ensures data matches Review model fields.
    """
    logger.info(f"Starting FULL review ingestion for company_id={company_id}")

    try:
        # 1. Fetch data ONLY from Business API
        reviews_data = await _fetch_reviews_from_business_api(place_id)

        if not reviews_data:
            logger.warning("⚠️ No reviews fetched. Check token validity or location access.")
            return

        async with get_session() as session:
            # 2. Start explicit transaction
            async with session.begin():
                for r in reviews_data:
                    # Map unique ID (Required: google_review_id)
                    g_id = r.get("reviewId")

                    # Map and format time (Required: google_review_time)
                    g_time = None
                    if "createTime" in r:
                        g_time = datetime.fromisoformat(r["createTime"].replace("Z", "+00:00"))
                    else:
                        # Fallback to current time if Business API missing createTime
                        g_time = datetime.now(timezone.utc)

                    # 3. Prevent duplicates
                    existing = await session.execute(
                        select(Review).where(Review.google_review_id == g_id)
                    )
                    if existing.scalar_one_or_none():
                        continue

                    # 4. Create Review object
                    new_review = Review(
                        company_id=company_id,
                        google_review_id=g_id,       # Required
                        author_name=r.get("reviewer", {}).get("displayName"),
                        rating=int(r.get("starRating", 0)), # Business API uses starRating
                        text=r.get("comment") or "",        # Business API uses comment
                        google_review_time=g_time,   # Required
                        profile_photo_url=r.get("reviewer", {}).get("profilePhotoUrl"),
                    )
                    session.add(new_review)

                # Automatically COMMITS all fetched history here 💾
        
        logger.info(f"✅ Full ingestion completed. Processed {len(reviews_data)} reviews.")

    except Exception as e:
        logger.error(f"❌ Review ingestion failed: {e}")
