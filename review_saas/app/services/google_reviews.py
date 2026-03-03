# File: app/services/google_reviews.py

from __future__ import annotations
import logging
from typing import Dict, Any, List

import googlemaps
from app.core.config import settings

logger = logging.getLogger("app.google")

# Initialize Google Maps Client
gmaps = googlemaps.Client(key=settings.GOOGLE_API_KEY)


# ---------------------------------------------------------
# Fetch full place details (used in reviews.py import)
# ---------------------------------------------------------
async def fetch_place_details(place_id: str) -> Dict[str, Any]:
    """
    Fetch place details from Google Places API.
    This is the function your reviews.py is trying to import.
    """

    try:
        response = gmaps.place(
            place_id=place_id,
            fields=[
                "name",
                "formatted_address",
                "formatted_phone_number",
                "website",
                "rating",
                "user_ratings_total",
                "reviews",
                "types",
                "opening_hours",
            ],
        )

        result = response.get("result", {})

        logger.info(f"✓ Google place details fetched for {place_id}")

        return result

    except Exception as e:
        logger.error(f"❌ Google API error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------
# Fetch only reviews (optional helper)
# ---------------------------------------------------------
async def fetch_reviews(place_id: str) -> List[Dict[str, Any]]:
    """
    Fetch reviews only from Google Places API.
    """

    try:
        response = gmaps.place(
            place_id=place_id,
            fields=["reviews"],
        )

        reviews = response.get("result", {}).get("reviews", [])

        logger.info(f"✓ {len(reviews)} reviews fetched from Google")

        return reviews

    except Exception as e:
        logger.error(f"❌ Failed to fetch reviews: {e}")
        return []
