# filename: app/services/google_reviews.py

import logging
import httpx
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review
from app.core.config import settings

logger = logging.getLogger(__name__)

# Use the specific key name from your configuration
API_KEY = settings.GOOGLE_BUSINESS_API_KEY

async def ingest_company_reviews(company_id: int, place_id: str):
    """
    Fetch reviews for a business.
    Phase 1: Uses Places API (via API Key) for the latest 5 public reviews.
    Phase 2: Ready for Business Profile API (v4) once Quota is approved.
    """

    logger.info(f"🔍 Fetching reviews for company_id={company_id}, place_id={place_id}")

    # For now, we use the Places API endpoint as the primary 'Discovery' source
    # because the Business Information API requires Account/Location IDs.
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "reviews",
        "key": API_KEY
    }

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data.get("status") != "OK":
                logger.error(f"❌ Google API Error: {data.get('status')} - {data.get('error_message')}")
                return

            reviews_data = data.get("result", {}).get("reviews", [])

            if not reviews_data:
                logger.warning(f"⚠️ No reviews found for place_id={place_id}")
                return

            async with get_session() as session:
                inserted_count = 0
                
                for r in reviews_data:
                    # Create a unique ID to prevent database duplicates
                    # We combine G (Google), the place_id, and the review timestamp
                    g_id = f"G_{place_id}_{r.get('time')}"

                    # 1. Check if review already exists
                    stmt = select(Review).where(Review.google_review_id == g_id)
                    existing = await session.execute(stmt)
                    if existing.scalar_one_or_none():
                        continue

                    # 2. Add new review record
                    new_review = Review(
                        company_id=company_id,
                        google_review_id=g_id,
                        author_name=r.get("author_name") or "Anonymous",
                        rating=int(r.get("rating", 0)),
                        text=r.get("text") or "",
                        google_review_time=datetime.fromtimestamp(
                            r.get("time", int(datetime.now().timestamp())), 
                            tz=timezone.utc
                        ),
                        profile_photo_url=r.get("profile_photo_url"),
                        reviewer_is_anonymous=False
                    )
                    
                    session.add(new_review)
                    inserted_count += 1

                # Commit all new reviews at once
                await session.commit()
                logger.info(f"✅ Successfully ingested {inserted_count} new reviews.")

        except Exception as e:
            logger.error(f"❌ Failed to ingest reviews: {str(e)}")
