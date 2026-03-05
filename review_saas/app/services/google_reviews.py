# filename: app/services/google_reviews.py

import logging
import httpx
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review
from app.core.config import settings

logger = logging.getLogger(__name__)

async def ingest_company_reviews(company_id: int, account_id: str, location_id: str, access_token: str):
    """
    Fetch ALL reviews for a business using the Google Business Profile API.
    Bypasses the 5-review limit by paginating through all available records.
    """
    # Use the Business Profile API endpoint (v4)
    base_url = f"https://mybusiness.googleapis.com/v4/accounts/{account_id}/locations/{location_id}/reviews"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    next_page_token = None
    total_synced = 0

    logger.info(f"🚀 Starting full review sync for company_id={company_id}")

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            while True:
                # Add pagination token to params if it exists from the previous loop
                params = {}
                if next_page_token:
                    params["pageToken"] = next_page_token
                
                response = await client.get(base_url, headers=headers, params=params)
                
                if response.status_code == 401:
                    logger.error("❌ Access Token expired or invalid.")
                    return
                elif response.status_code != 200:
                    logger.error(f"❌ Google API Error: {response.status_code} - {response.text}")
                    break

                data = response.json()
                reviews_data = data.get("reviews", [])

                if not reviews_data:
                    logger.info("ℹ️ No reviews found for this location.")
                    break

                async with get_session() as session:
                    for r in reviews_data:
                        # Use the official Google Review ID
                        g_id = r.get("reviewId")

                        # 1. Check for duplicates
                        stmt = select(Review).where(Review.google_review_id == g_id)
                        existing = await session.execute(stmt)
                        if existing.scalar_one_or_none():
                            continue

                        # 2. Add new review
                        # starRating comes as 'STAR_RATING_5', we extract the '5'
                        rating_str = r.get("starRating", "STAR_RATING_0")
                        numeric_rating = int(rating_str.split("_")[-1])

                        session.add(Review(
                            company_id=company_id,
                            google_review_id=g_id,
                            author_name=r.get("reviewer", {}).get("displayName", "Anonymous"),
                            rating=numeric_rating,
                            text=r.get("comment", ""),
                            # Parse ISO 8601 strings (e.g., 2026-03-05T10:00:00Z)
                            google_review_time=datetime.fromisoformat(
                                r.get("createTime").replace("Z", "+00:00")
                            ),
                            profile_photo_url=r.get("reviewer", {}).get("profilePhotoUrl"),
                            review_reply_text=r.get("reviewReply", {}).get("comment"),
                            review_reply_time=datetime.fromisoformat(
                                r.get("reviewReply", {}).get("updateTime").replace("Z", "+00:00")
                            ) if r.get("reviewReply") else None
                        ))
                        total_synced += 1
                    
                    await session.commit()

                # 3. Check for nextPageToken to continue the loop
                next_page_token = data.get("nextPageToken")
                if not next_page_token:
                    logger.info(f"🏁 Reached end of reviews. Total synced: {total_synced}")
                    break

        except Exception as e:
            logger.error(f"❌ Critical error during full review ingestion: {e}")

async def fetch_place_details(place_id: str):
    """
    Helper to get basic business info using the API Key.
    """
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address",
        "key": settings.GOOGLE_BUSINESS_API_KEY
    }
    async with httpx.AsyncClient() as client:
        res = await client.get(url, params=params)
        return res.json().get("result")
