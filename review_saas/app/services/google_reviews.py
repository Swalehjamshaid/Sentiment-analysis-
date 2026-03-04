# filename: app/services/google_reviews.py

import logging
import httpx
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review
from app.core.config import settings

logger = logging.getLogger(__name__)

# YOUR API KEY
API_KEY = "AIzaSyDjQFzX3Wak4maUWhSXstPmnbBOOKGVGfc"

async def fetch_place_details(place_id: str):
    """
    Restored function to fix the ImportError.
    Fetches basic business info using your API Key.
    """
    url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=name,formatted_address&key={API_KEY}"
    
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

async def ingest_company_reviews(company_id: int, place_id: str):
    """
    Fetches reviews using your API Key. 
    Note: Google limits this to 5 reviews for 'Public' API Keys.
    """
    logger.info(f"Starting ingestion for company {company_id}")
    url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=reviews&key={API_KEY}"

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            response = await client.get(url)
            reviews_data = response.json().get("result", {}).get("reviews", [])
            
            async with get_session() as session:
                async with session.begin():
                    for r in reviews_data:
                        # Create a unique ID for the review
                        g_id = f"G_{place_id}_{r.get('time')}"
                        
                        # Check if already exists
                        exists = await session.execute(select(Review).where(Review.google_review_id == g_id))
                        if exists.scalar_one_or_none():
                            continue

                        session.add(Review(
                            company_id=company_id,
                            google_review_id=g_id,
                            author_name=r.get("author_name"),
                            rating=int(r.get("rating", 0)),
                            text=r.get("text", ""),
                            google_review_time=datetime.fromtimestamp(r["time"], tz=timezone.utc),
                            profile_photo_url=r.get("profile_photo_url")
                        ))
            logger.info(f"Successfully ingested {len(reviews_data)} reviews.")
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
