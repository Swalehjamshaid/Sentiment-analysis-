# filename: app/services/google_reviews.py

import logging
import httpx
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review
from app.core.config import settings

logger = logging.getLogger(__name__)

# --- RESTORED FOR COMPATIBILITY ---
async def fetch_place_details(place_id: str):
    """
    Fetch basic business details using the Business API.
    Used by the router to get the company name.
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
            "address": data.get("address", {}).get("addressLines", [""])[0]
        }

# --- REMAINING BUSINESS API FUNCTIONS ---
async def _fetch_reviews_from_business_api(place_id: str):
    token = getattr(settings, "GOOGLE_BUSINESS_ACCESS_TOKEN", None)
    if not token: return None
    url = f"https://mybusiness.googleapis.com/v4/accounts/-/locations/{place_id}/reviews"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(url, headers=headers)
        return res.json().get("reviews") if res.status_code == 200 else None

async def ingest_company_reviews(company_id: int, place_id: str):
    logger.info(f"Starting FULL ingestion for company_id={company_id}")
    try:
        reviews_data = await _fetch_reviews_from_business_api(place_id)
        if not reviews_data: return
        async with get_session() as session:
            async with session.begin():
                for r in reviews_data:
                    g_id = r.get("reviewId")
                    g_time = datetime.fromisoformat(r["createTime"].replace("Z", "+00:00")) if "createTime" in r else datetime.now(timezone.utc)
                    
                    exists = await session.execute(select(Review).where(Review.google_review_id == g_id))
                    if exists.scalar_one_or_none(): continue

                    session.add(Review(
                        company_id=company_id,
                        google_review_id=g_id,
                        author_name=r.get("reviewer", {}).get("displayName"),
                        rating=int(r.get("starRating", "").replace("STAR_RATING_", "") or 0),
                        text=r.get("comment") or "",
                        google_review_time=g_time,
                        profile_photo_url=r.get("reviewer", {}).get("profilePhotoUrl")
                    ))
        logger.info(f"✅ Full sync complete. Processed {len(reviews_data)} reviews.")
    except Exception as e:
        logger.error(f"❌ Ingestion failed: {e}")
