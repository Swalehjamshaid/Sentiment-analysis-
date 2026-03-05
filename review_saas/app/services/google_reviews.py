# filename: app/services/google_reviews.py

import logging
import httpx
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review
from app.core.config import settings

logger = logging.getLogger(__name__)

# Note: Full history requires the Business Profile API (v4) and OAuth Token
# Public Places API Key will still only return the top 5.

async def ingest_all_business_reviews(
    company_id: int, 
    account_id: str, 
    location_id: str, 
    access_token: str
):
    """
    Fetch ALL reviews for a business using the Business Profile API.
    Bypasses the 5-review limit via pagination (nextPageToken).
    """
    # Endpoint for the Business Profile Reviews API
    base_url = f"https://mybusiness.googleapis.com/v4/accounts/{account_id}/locations/{location_id}/reviews"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    next_page_token = None
    total_new_reviews = 0

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            while True:
                # Add pagination token if we have one
                params = {"pageToken": next_page_token} if next_page_token else {}
                
                response = await client.get(base_url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                
                reviews_data = data.get("reviews", [])
                if not reviews_data:
                    break

                async with get_session() as session:
                    for r in reviews_data:
                        # Business API unique ID
                        g_id = r.get("reviewId")

                        # Duplicate check
                        stmt = select(Review).where(Review.google_review_id == g_id)
                        existing = await session.execute(stmt)
                        if existing.scalar_one_or_none():
                            continue

                        # Map API fields to your DB Model
                        session.add(Review(
                            company_id=company_id,
                            google_review_id=g_id,
                            author_name=r.get("reviewer", {}).get("displayName", "Anonymous"),
                            rating=int(r.get("starRating", "0").replace("STAR_RATING_", "")),
                            text=r.get("comment", ""),
                            google_review_time=datetime.fromisoformat(
                                r.get("createTime").replace("Z", "+00:00")
                            ),
                            profile_photo_url=r.get("reviewer", {}).get("profilePhotoUrl"),
                            review_reply_text=r.get("reviewReply", {}).get("comment"),
                            # Handle reply time if it exists
                            review_reply_time=datetime.fromisoformat(
                                r.get("reviewReply", {}).get("updateTime").replace("Z", "+00:00")
                            ) if r.get("reviewReply") else None
                        ))
                        total_new_reviews += 1
                    
                    await session.commit()

                # Check if there's another page
                next_page_token = data.get("nextPageToken")
                if not next_page_token:
                    break
            
            logger.info(f"✅ Sync Complete: Added {total_new_reviews} reviews for company {company_id}.")

        except httpx.HTTPStatusError as e:
            logger.error(f"❌ API Error ({e.response.status_code}): {e.response.text}")
        except Exception as e:
            logger.error(f"❌ Critical Error during full sync: {e}")
