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
# Google Business API: Location Details
# ---------------------------------------------------------
async def fetch_place_details(place_id: str):
    """
    Fetch basic business details using the Business API.
    Aligned with the Company table structure.
    """
    token = getattr(settings, "GOOGLE_BUSINESS_ACCESS_TOKEN", None)
    if not token:
        logger.error("GOOGLE_BUSINESS_ACCESS_TOKEN missing in configuration")
        return {}

    # Endpoint for specific location details
    url = f"https://mybusiness.googleapis.com/v4/accounts/-/locations/{place_id}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                logger.error(f"Details fetch failed: {response.status_code}")
                return {}
            
            data = response.json()
            return {
                "name": data.get("locationName"),
                "address": data.get("address", {}).get("addressLines", [""])[0] if data.get("address") else ""
            }
        except Exception as e:
            logger.error(f"Place details connection error: {e}")
            return {}

# ---------------------------------------------------------
# Google Business API: Raw Review Fetch
# ---------------------------------------------------------
async def _fetch_reviews_from_business_api(place_id: str):
    """
    Fetches raw review JSON data from the Google Business Profile API.
    """
    token = getattr(settings, "GOOGLE_BUSINESS_ACCESS_TOKEN", None)
    if not token: 
        logger.error("Cannot fetch: GOOGLE_BUSINESS_ACCESS_TOKEN is null")
        return None
    
    url = f"https://mybusiness.googleapis.com/v4/accounts/-/locations/{place_id}/reviews"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            res = await client.get(url, headers=headers)
            if res.status_code != 200:
                logger.error(f"Business API error: {res.status_code} - {res.text}")
                return None
            return res.json().get("reviews", [])
        except Exception as e:
            logger.error(f"Business API connection failed: {e}")
            return None

# ---------------------------------------------------------
# Main Ingestion Logic: Alignment & Database Commit
# ---------------------------------------------------------
async def ingest_company_reviews(company_id: int, place_id: str):
    """
    Ingests reviews and strictly maps them to app/core/models.py fields.
    Ensures google_review_id, rating, and google_review_time constraints are met.
    """
    logger.info(f"Starting FULL history ingestion for company_id={company_id}")
    
    try:
        # 1. Fetch raw data from the Business API
        reviews_data = await _fetch_reviews_from_business_api(place_id)
        if not reviews_data:
            logger.warning(f"Ingestion aborted: No reviews returned for place {place_id}")
            return

        async with get_session() as session:
            # 2. Use session.begin() for atomic transaction (COMMIT if success, ROLLBACK if fail)
            async with session.begin():
                for r in reviews_data:
                    # Map unique Google ID (Required: nullable=False)
                    g_id = r.get("reviewId")
                    if not g_id:
                        continue

                    # 3. Check for duplicates using the unique ID field
                    exists = await session.execute(
                        select(Review).where(Review.google_review_id == g_id)
                    )
                    if exists.scalar_one_or_none():
                        continue

                    # 4. Map Time (Required: google_review_time)
                    g_time = None
                    if "createTime" in r:
                        # API uses 'Z' suffix, replace for Python's ISO parser
                        g_time = datetime.fromisoformat(r["createTime"].replace("Z", "+00:00"))
                    else:
                        g_time = datetime.now(timezone.utc)

                    # 5. Map Rating (Required: rating as Integer)
                    # Converts "STAR_RATING_5" string to integer 5
                    raw_rating = r.get("starRating", "STAR_RATING_UNSPECIFIED")
                    clean_rating = 0
                    if "STAR_RATING_" in raw_rating:
                        try:
                            clean_rating = int(raw_rating.replace("STAR_RATING_", ""))
                        except (ValueError, TypeError):
                            clean_rating = 0

                    # 6. Populate model instance with strict field alignment
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
                    
        logger.info(f"✅ Ingestion complete. Successfully synced {len(reviews_data)} reviews to Postgres.")

    except Exception as e:
        logger.error(f"❌ Critical error during review ingestion: {e}")
