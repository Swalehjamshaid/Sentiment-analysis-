# filename: app/services/google_reviews.py
from __future__ import annotations
import googlemaps
import logging
from datetime import datetime, timezone
from ..core.settings import settings

# Requirement #130: Dedicated logger for API tracking
logger = logging.getLogger('app.google_reviews')

class GoogleReviewsService:
    def __init__(self):
        # Requirement #128: Google Places API Integration
        # Using the key from your Railway Variable: GOOGLE_PLACES_API_KEY
        if not settings.GOOGLE_PLACES_API_KEY:
            logger.error("GOOGLE_PLACES_API_KEY is missing in Railway Variables!")
            self.client = None
        else:
            try:
                self.client = googlemaps.Client(key=settings.GOOGLE_PLACES_API_KEY)
                logger.info("Google Maps Client initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize Google Client: {e}")
                self.client = None

    def validate_business(self, place_id: str) -> dict | None:
        """Requirement #35: Validate Place ID before saving."""
        if not self.client:
            logger.error("API Call Aborted: Google Client not initialized.")
            return None
        try:
            logger.info(f"API REQUEST: Validating Place ID: {place_id}")
            place = self.client.place(
                place_id=place_id, 
                fields=['name', 'formatted_address', 'geometry', 'place_id']
            )
            if place.get('status') == 'OK':
                logger.info(f"API SUCCESS: Validated {place['result'].get('name')}")
                return place.get('result')
            else:
                logger.warning(f"API WARNING: Google returned status {place.get('status')}")
                return None
        except Exception as e:
            logger.error(f"Requirement #49: API Validation error: {e}")
            return None

    def fetch_latest_reviews(self, place_id: str):
        """Requirement #52: Fetch reviews for storage."""
        if not self.client:
            return []
        try:
            logger.info(f"API REQUEST: Fetching reviews for Place ID: {place_id}")
            result = self.client.place(place_id=place_id, fields=['review'])
            if result.get('status') == 'OK':
                reviews = result.get('result').get('reviews', [])
                logger.info(f"API SUCCESS: Retrieved {len(reviews)} reviews.")
                return reviews
            return []
        except Exception as e:
            logger.error(f"Requirement #57: API fetch error: {e}")
            return []

# Initialize singleton instance
google_api = GoogleReviewsService()

# Standalone function for scheduler (Requirement #54)
def fetch_reviews(place_id: str):
    return google_api.fetch_latest_reviews(place_id)
