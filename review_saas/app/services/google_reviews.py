# filename: app/services/google_reviews.py

import logging
import httpx
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review
from app.core.config import settings

logger = logging.getLogger(__name__)

# This matches the key name in your Railway environment variables
API_KEY = settings.GOOGLE_BUSINESS_API_KEY

async def fetch_place_details(place_id: str):
    """
    Fetch basic details for a place (Name, Address, Status) from Google Places API.
    Required by routes/reviews.py to confirm which restaurant was fetched.
    """
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,rating,user_ratings_total,business_status",
        "key": API_KEY
    }
    
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "OK":
                return data.get("result", {})
            else:
                logger.error(f"❌ Google Places API Error: {data.get('status')}")
                return None
        except Exception as e:
            logger.error(f"❌ Failed to fetch place details: {e}")
            return None

async def ingest_company_reviews(company_id: int, place_id: str):
    """
    Fetch reviews for a business and store them in the database.
    """
    logger.info(f"🔍 Fetching reviews for company_id={company_id}, place_id={place_id}")

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
                    # Create a unique ID: G_{place_id}_{timestamp}
                    g_id = f"G_{place_id}_{r.get('time')}"

                    # 1. Check if review already exists to prevent duplicates
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

                await session.commit()
                logger.info(f"✅ Ingested {inserted_count} reviews for company {company_id}.")

        except Exception as e:
            logger.error(f"❌ Failed to ingest reviews: {str(e)}")
