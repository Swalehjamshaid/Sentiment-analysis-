# filename: app/services/google_reviews.py

import logging
import httpx
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review
from app.core.config import settings

logger = logging.getLogger(__name__)

async def _fetch_reviews_from_google(place_id: str):
    """
    Attempts to fetch reviews using the provided API Key.
    NOTE: Using an API Key (AIza...) typically limits results to 5.
    """
    # Using the key you provided
    api_key = "AIzaSyDjQFzX3Wak4maUWhSXstPmnbBOOKGVGfc"
    
    # This is the Places API endpoint (supports API Keys)
    url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=reviews&key={api_key}"

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url)
            result = response.json().get("result", {})
            reviews = result.get("reviews", [])
            
            if len(reviews) == 5:
                logger.warning("⚠️ Only 5 reviews fetched. This is a limit of using an API Key.")
            
            return reviews
        except Exception as e:
            logger.error(f"❌ Google API connection failed: {e}")
            return None

async def ingest_company_reviews(company_id: int, place_id: str):
    """
    Ingests reviews into Postgres based on the API Key results.
    """
    logger.info(f"🚀 Starting sync for company_id={company_id} using API Key.")
    
    reviews_data = await _fetch_reviews_from_google(place_id)
    if not reviews_data:
        return

    async with get_session() as session:
        async with session.begin():
            for r in reviews_data:
                # Generate a unique ID since Places API doesn't provide a 'reviewId' field
                g_id = f"{place_id}_{r.get('time')}_{r.get('author_name')[:5]}"
                
                # Convert timestamp to datetime
                g_time = datetime.fromtimestamp(r["time"], tz=timezone.utc) if "time" in r else datetime.now(timezone.utc)
                
                # Duplicate check
                exists = await session.execute(select(Review).where(Review.google_review_id == g_id))
                if exists.scalar_one_or_none():
                    continue

                session.add(Review(
                    company_id=company_id,
                    google_review_id=g_id,
                    author_name=r.get("author_name"),
                    rating=int(r.get("rating", 0)),
                    text=r.get("text") or "",
                    google_review_time=g_time,
                    profile_photo_url=r.get("profile_photo_url")
                ))
    logger.info(f"✅ Sync complete. Processed {len(reviews_data)} reviews.")
