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
# Google Business API (Full History Fetch)
# ---------------------------------------------------------
async def _fetch_reviews_from_business_api(place_id: str):
    """
    Fetches full review history using the Google Business Profile API.
    """
    access_token = getattr(settings, "GOOGLE_BUSINESS_ACCESS_TOKEN", None)
    if not access_token:
        logger.error("❌ GOOGLE_BUSINESS_ACCESS_TOKEN not found in settings.")
        return None

    # Use the locations endpoint for full history
    url = f"https://mybusiness.googleapis.com/v4/accounts/-/locations/{place_id}/reviews"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                logger.error(f"❌ Business API Error {response.status_code}: {response.text}")
                return None
            return response.json().get("reviews", [])
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            return None

# ---------------------------------------------------------
# Main Ingestion Function
# ---------------------------------------------------------
async def ingest_company_reviews(company_id: int, place_id: str):
    """
    Strictly uses Business API to pull data into Postgres.
    """
    logger.info(f"Starting FULL history ingestion for company_id={company_id}")

    try:
        # 1. Fetch data from Business API
        reviews_data = await _fetch_reviews_from_business_api(place_id)
        if not reviews_data:
            logger.warning("No reviews returned from Business API.")
            return

        async with get_session() as session:
            # 2. Use a transaction block for atomic saving
            async with session.begin():
                for r in reviews_data:
                    g_id = r.get("reviewId")
                    
                    # Map the Business API 'createTime'
                    g_time = None
                    if "createTime" in r:
                        g_time = datetime.fromisoformat(r["createTime"].replace("Z", "+00:00"))
                    else:
                        g_time = datetime.now(timezone.utc)

                    # 3. Check for duplicates in Postgres
                    existing = await session.execute(
                        select(Review).where(Review.google_review_id == g_id)
                    )
                    if existing.scalar_one_or_none():
                        continue

                    # 4. Create model using Business API specific fields
                    new_review = Review(
                        company_id=company_id,
                        google_review_id=g_id,
                        author_name=r.get("reviewer", {}).get("displayName"),
                        rating=int(r.get("starRating", "").replace("STAR_RATING_", "") or 0),
                        text=r.get("comment") or "",
                        google_review_time=g_time, # Matches your model
                        profile_photo_url=r.get("reviewer", {}).get("profilePhotoUrl")
                    )
                    session.add(new_review)
        
        logger.info(f"✅ Full sync complete. Saved {len(reviews_data)} reviews.")

    except Exception as e:
        logger.error(f"❌ Ingestion process failed: {e}")
