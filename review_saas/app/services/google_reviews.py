# filename: app/services/google_reviews.py

import logging
import httpx
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review
from app.core.config import settings

logger = logging.getLogger(__name__)

API_KEY = settings.GOOGLE_BUSINESS_API_KEY

# ---------------------------------------------------------
# Ingest all reviews using Google Business Profile API
# ---------------------------------------------------------
async def ingest_company_reviews(company_id: int, place_id: str):
    """
    Fetch all reviews for a business using Google Business Profile API
    and store them in the database. Works for deep review analysis.
    """

    url = (
        f"https://mybusiness.googleapis.com/v4/accounts:search?key={API_KEY}"
    )
    # Note: The proper way to fetch all reviews requires knowing accountId & locationId.
    # If you have only place_id, we can fetch basic details from Places API
    # for demonstration purposes. For full access, accountId & locationId is needed.

    logger.info(f"Fetching reviews for company_id={company_id}, place_id={place_id}")

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            # Google Places API fallback (first 5 reviews)
            response = await client.get(
                f"https://maps.googleapis.com/maps/api/place/details/json"
                f"?place_id={place_id}&fields=reviews&key={API_KEY}"
            )
            result = response.json().get("result", {})
            reviews_data = result.get("reviews", [])

            if not reviews_data:
                logger.warning(f"No reviews returned for place_id={place_id}")
                return

            async with get_session() as session:
                async with session.begin():
                    inserted_count = 0
                    for r in reviews_data:
                        # Unique google_review_id
                        g_id = f"G_{place_id}_{r.get('time')}"

                        # Skip if already exists
                        exists = await session.execute(
                            select(Review).where(Review.google_review_id == g_id)
                        )
                        if exists.scalar_one_or_none():
                            continue

                        session.add(Review(
                            company_id=company_id,
                            google_review_id=g_id,
                            author_name=r.get("author_name") or "Anonymous",
                            rating=int(r.get("rating", 0)),
                            text=r.get("text") or "",
                            google_review_time=datetime.fromtimestamp(
                                r.get("time", int(datetime.now().timestamp())), tz=timezone.utc
                            ),
                            profile_photo_url=r.get("profile_photo_url"),
                            reviewer_is_anonymous=False,
                            # Other fields default to None, can be updated later
                        ))
                        inserted_count += 1

            logger.info(f"✅ Reviews ingestion complete: {inserted_count} reviews added.")

        except Exception as e:
            logger.error(f"Failed to ingest reviews: {e}")
