# File: review_saas/app/services/google_reviews.py
import httpx
import logging
from typing import List, Dict, Any, Optional
from app.core.config import settings

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
                logger.error(f"Auth error: {str(e)}")
                return None

    async def fetch_reviews(self, account_id: str, location_id: str) -> List[Dict[str, Any]]:
        """Fetches reviews from Google Business API using OAuth2."""
        token = await self.get_access_token()
        if not token:
            return []

        url = f"https://mybusiness.googleapis.com/v4/accounts/{account_id}/locations/{location_id}/reviews"
        headers = {"Authorization": f"Bearer {token}"}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                return response.json().get("reviews", [])
            return []

# Initialize Service Instance
google_reviews_service = GoogleReviewsService()

# --- THE FUNCTIONS BELOW FIX THE IMPORT ERRORS ---

async def fetch_place_details(place_id: str) -> Dict[str, Any]:
    """
    Fetches details for a place using the Google Places API.
    Used by app/routes/reviews.py
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
            logger.error(f"Failed to fetch place details: {str(e)}")
            return {}

async def ingest_company_reviews(account_id: str, location_id: str):
    """
    Wrapper function to ingest reviews.
    Used by app/routes/companies.py
    """
    try:
        return await google_reviews_service.fetch_reviews(account_id, location_id)
    except Exception as e:
        logger.error(f"Ingestion failed: {str(e)}")
        return []
