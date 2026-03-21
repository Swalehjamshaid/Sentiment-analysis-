# filename: app/services/scraper.py

import os
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

from google.maps import Client as GoogleMapsClient

logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


# ─────────────────────────────────────────────
# INIT GOOGLE CLIENT
# ─────────────────────────────────────────────
def get_client():
    if not GOOGLE_API_KEY:
        raise ValueError("❌ GOOGLE_API_KEY not set in environment")
    return GoogleMapsClient(key=GOOGLE_API_KEY)


# ─────────────────────────────────────────────
# FETCH PLACE DETAILS (GOOGLE LIBRARY)
# ─────────────────────────────────────────────
def _get_place_details(place_id: str) -> Dict[str, Any]:
    client = get_client()

    response = client.place(
        place_id=place_id,
        fields=[
            "name",
            "rating",
            "user_ratings_total",
            "reviews"
        ]
    )

    if response.get("status") != "OK":
        logger.error(f"❌ Google API error: {response}")
        return {}

    return response.get("result", {})


# ─────────────────────────────────────────────
# TRANSFORM DATA → YOUR FORMAT
# ─────────────────────────────────────────────
def _transform_reviews(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    reviews = []

    for r in data.get("reviews", []):
        try:
            reviews.append({
                "review_id": str(r.get("time")),  # unique enough
                "rating": int(r.get("rating", 0)),
                "text": r.get("text", ""),
                "author_name": r.get("author_name", "Anonymous"),
                "google_review_time": datetime.fromtimestamp(
                    r.get("time", 0),
                    tz=timezone.utc
                ).isoformat()
            })
        except Exception:
            continue

    return reviews


# ─────────────────────────────────────────────
# MAIN FUNCTION (YOUR PROJECT ENTRY POINT)
# ─────────────────────────────────────────────
async def fetch_reviews(place_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    ✔ Fully aligned with your routes/reviews.py
    ✔ Uses official Google Maps Python library
    ✔ No Playwright / No scraping
    """

    logger.info(f"🚀 Fetching Google reviews via library for place_id: {place_id}")

    try:
        data = _get_place_details(place_id)

        if not data:
            return []

        reviews = _transform_reviews(data)

        logger.info(f"✅ Retrieved {len(reviews)} reviews")

        return reviews[:limit]

    except Exception as e:
        logger.error(f"❌ Fetch failed: {str(e)}", exc_info=True)
        return []
