# filename: app/services/scraper.py
import logging
from datetime import datetime
from typing import List, Dict, Any

import googlemaps

logger = logging.getLogger(__name__)

# ── Initialize Google Maps Client ──
# Make sure to set your API key in environment variable or directly here
# Example: export GOOGLE_MAPS_API_KEY="YOUR_KEY"
import os
API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "YOUR_API_KEY_HERE")
gmaps = googlemaps.Client(key=API_KEY)


def parse_relative_time(relative_time_str: str) -> datetime:
    """
    Converts Google's relative time string (e.g., "2 weeks ago") into datetime.
    """
    from datetime import timedelta
    now = datetime.utcnow()
    number = 1
    if not relative_time_str:
        return now

    text = relative_time_str.lower()
    for part in text.split():
        if part.isdigit():
            number = int(part)
            break

    if "minute" in text:
        return now - timedelta(minutes=number)
    if "hour" in text:
        return now - timedelta(hours=number)
    if "day" in text:
        return now - timedelta(days=number)
    if "week" in text:
        return now - timedelta(weeks=number)
    if "month" in text:
        return now - timedelta(days=number * 30)
    if "year" in text:
        return now - timedelta(days=number * 365)
    return now


def fetch_google_reviews(place_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Fetch reviews and ratings from Google Maps using official Google Maps API.
    Returns a list of review dictionaries with author, rating, text, and time.
    """
    reviews_data = []

    try:
        logger.info(f"🚀 Fetching Google reviews for place_id: {place_id}")

        # Request place details including reviews
        response = gmaps.place(
            place_id=place_id,
            fields=["name", "rating", "user_ratings_total", "reviews"]
        )

        result = response.get("result", {})
        reviews = result.get("reviews", [])

        for r in reviews[:limit]:
            reviews_data.append({
                "review_id": r.get("author_url", "")[-32:],  # unique identifier fallback
                "author_name": r.get("author_name", "Google User"),
                "rating": r.get("rating", 0),
                "text": r.get("text", ""),
                "google_review_time": parse_relative_time(r.get("relative_time_description", ""))
                    .isoformat()
            })

        logger.info(f"✅ Fetched {len(reviews_data)} reviews for place_id: {place_id}")
        return reviews_data

    except Exception as e:
        logger.error(f"❌ Failed to fetch reviews for place_id {place_id}: {str(e)[:200]}")
        return []


def fetch_google_rating(place_id: str) -> Dict[str, Any]:
    """
    Fetch overall rating and total number of reviews from Google Maps.
    """
    try:
        response = gmaps.place(
            place_id=place_id,
            fields=["name", "rating", "user_ratings_total"]
        )
        result = response.get("result", {})
        rating = result.get("rating", 0)
        total_reviews = result.get("user_ratings_total", 0)
        logger.info(f"📊 Rating for place_id {place_id}: {rating} ({total_reviews} reviews)")
        return {"rating": rating, "total_reviews": total_reviews}

    except Exception as e:
        logger.error(f"❌ Failed to fetch rating for place_id {place_id}: {str(e)[:200]}")
        return {"rating": 0, "total_reviews": 0}
