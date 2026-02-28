# filename: app/services/google_reviews.py
from __future__ import annotations
import googlemaps
import logging
from datetime import datetime, timezone
from ..core.settings import settings

logger = logging.getLogger('app.google_reviews')

class GoogleReviewsService:
    def __init__(self):
        # Requirement #128: Google Places API integration
        self.client = googlemaps.Client(key=settings.GOOGLE_PLACES_API_KEY)

    def validate_business(self, place_id: str) -> dict | None:
        """Requirement #35: Validate Place ID before saving."""
        try:
            place = self.client.place(
                place_id=place_id, 
                fields=['name', 'formatted_address', 'geometry', 'place_id']
            )
            if place.get('status') == 'OK':
                return place.get('result')
        except Exception as e:
            logger.error(f"Requirement #49: API Validation failed for {place_id}: {e}")
        return None

    def fetch_latest_reviews(self, place_id: str):
        """Requirement #52 & #55: Fetch reviews for storage."""
        try:
            result = self.client.place(
                place_id=place_id, 
                fields=['review']
            )
            if result.get('status') == 'OK':
                return result.get('result').get('reviews', [])
        except Exception as e:
            logger.error(f"Requirement #57: API error handling: {e}")
        return []

# Initialize instance
google_api = GoogleReviewsService()

# Standalone function for scheduler compatibility
def fetch_reviews(place_id: str):
    """Bridge function to resolve ImportErrors in scheduler.py"""
    return google_api.fetch_latest_reviews(place_id)
