# filename: app/services/google_reviews.py

import logging
import httpx
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review
from app.core.config import settings 

logger = logging.getLogger(__name__)

# Use the Google Business API key from settings
API_KEY = settings.GOOGLE_BUSINESS_API_KEY

# ---------------------------------------------------------
# Fetch basic place details (RESTORED TO FIX IMPORT ERROR)
# ---------------------------------------------------------
async def fetch_place_details(place_id: str):
    """
    Fetch basic business info using Google Places API.
    Returns name and address for the dashboard display.
    """
    url = (
        f"https://maps.googleapis.com/maps/api/place/details/json"
        f"?place_id={place_id}&fields=name,formatted_address&key={API_KEY}"
    )

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(url)
            data = response.json().get("result", {})
            return {
                "name": data.get("name", "Unknown Business"),
                "address": data.get("formatted_address", "")
            }
        except Exception as e:
            logger.error(f"Error fetching place details: {e}")
            return {"name": "Unknown", "address": ""}

# ---------------------------------------------------------
# Ingest reviews and store in database
# ---------------------------------------------------------
async def ingest_company_reviews(company_id: int, place_id: str):
    """
    Fetches Google Place reviews using Places API (up to 5 reviews)
    and stores them in the database. 
    """
    url = (
        f"https://maps.googleapis.com/maps/api/place/details/json"
        f"?place_id={place_id}&fields=reviews&key={API_KEY}"
    )

    logger.info(f"Fetching reviews for company_id={company_id}, place_id={place_id}")

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            response = await client.get(url)
            result = response.json().get("result", {})
            reviews_data = result.get("reviews", [])

            if not reviews_data:
                logger.warning(f"No reviews returned for place_id={place_id}")
                return

            async with get_session() as session:
                async with session.begin():
                    inserted_count = 0
                    for r in reviews_data:
                        # Create unique google_review_id
                        g_id = f"G_{place_id}_{r.get('time')}"

                        # Skip if already exists
                        exists = await session.execute(
                            select(Review).where(Review.google_review_id == g_id)
                        )
                        if exists.scalar_one_or_none():
                            continue

                        # Insert review aligned with your model
                        session.add(Review(
                            company_id=company_id,
                            google_review_id=g_id,
                            author_name=r.get("author_name") or "Anonymous",
                            rating=int(r.get("rating", 0)),
                            text=r.get("text") or "",
                            google_review_time=datetime.fromtimestamp(
                                r.get("time", int(datetime.now().timestamp())), tz=timezone.utc
                            ),
                            profile_photo_url=r.get("profile_photo_url") or None
                        ))
                        inserted_count += 1

            logger.info(f"✅ Ingestion complete: {inserted_count} reviews added.")

        except Exception as e:
            logger.error(f"Failed to ingest reviews: {e}")
