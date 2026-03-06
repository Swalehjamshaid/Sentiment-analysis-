# File: review_saas/app/services/google_reviews.py
import httpx
import logging
from typing import List, Dict, Any, Optional
from app.core.config import settings

# Configure logging for Railway dashboard visibility
logger = logging.getLogger(__name__)

class GoogleReviewsService:
    def __init__(self):
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        self.refresh_token = settings.GOOGLE_REFRESH_TOKEN
        self.token_url = "https://oauth2.googleapis.com/token"

    async def get_access_token(self) -> Optional[str]:
        """Exchanges refresh token for a fresh access token."""
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.token_url, data=data)
                if response.status_code == 200:
                    return response.json().get("access_token")
                logger.error(f"Token refresh failed: {response.text}")
                return None
            except Exception as e:
                logger.error(f"Auth error during token refresh: {str(e)}")
                return None

    async def fetch_reviews(self, account_id: str, location_id: str) -> List[Dict[str, Any]]:
        """
        Fetches ALL reviews from Google Business API using OAuth2 and Pagination.
        This fixes the issue where only 5 reviews were being displayed.
        """
        token = await self.get_access_token()
        if not token:
            logger.error("No access token available for fetching reviews.")
            return []

        all_reviews = []
        next_page_token = None
        
        # Base URL for the Google Business Profile reviews endpoint
        base_url = f"https://mybusiness.googleapis.com/v4/accounts/{account_id}/locations/{location_id}/reviews"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                # pageSize=50 is the maximum allowed by Google per request
                params = {"pageSize": 50}
                if next_page_token:
                    params["pageToken"] = next_page_token

                try:
                    response = await client.get(base_url, headers=headers, params=params)
                    
                    if response.status_code != 200:
                        logger.error(f"Google API Error: {response.status_code} - {response.text}")
                        break

                    data = response.json()
                    reviews = data.get("reviews", [])
                    all_reviews.extend(reviews)

                    # Check if there is another page of reviews (Pagination)
                    next_page_token = data.get("nextPageToken")
                    
                    # Stop if no more pages or if we hit a safety limit (e.g., 500 reviews)
                    if not next_page_token or len(all_reviews) >= 500:
                        break
                        
                except Exception as e:
                    logger.error(f"Error during Google review pagination loop: {str(e)}")
                    break

        logger.info(f"Successfully fetched {len(all_reviews)} reviews for location {location_id}")
        return all_reviews

# Initialize Service Instance for the application
google_reviews_service = GoogleReviewsService()

# --- HELPER FUNCTIONS FOR ROUTES ---

async def fetch_place_details(place_id: str) -> Dict[str, Any]:
    """
    Fetches details for a place using the Google Places API.
    Required by app/routes/reviews.py to resolve ImportErrors.
    """
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "key": settings.GOOGLE_PLACES_API_KEY
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                return response.json().get("result", {})
            logger.error(f"Google Places API error: {response.text}")
            return {}
        except Exception as e:
            logger.error(f"Failed to fetch place details for {place_id}: {str(e)}")
            return {}

async def ingest_company_reviews(account_id: str, location_id: str):
    """
    Top-level function to trigger review ingestion.
    Required by app/routes/companies.py to resolve ImportErrors.
    """
    try:
        return await google_reviews_service.fetch_reviews(account_id, location_id)
    except Exception as e:
        logger.error(f"Ingestion failed for {location_id}: {str(e)}")
        return []
