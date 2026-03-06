import httpx
import logging
from typing import List, Dict, Any, Optional
from app.core.config import settings

# Configure logging to see errors in Railway Deploy Logs
logger = logging.getLogger(__name__)

class GoogleReviewsService:
    """
    Service to interact with Google Business Profile API using OAuth 2.0.
    Requires GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN.
    """
    
    def __init__(self):
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        self.refresh_token = settings.GOOGLE_REFRESH_TOKEN
        self.token_url = "https://oauth2.googleapis.com/token"
        # Base URL for the Google Business Profile API
        self.api_base_url = "https://mybusinessbusinessinformation.googleapis.com/v1"

    async def get_access_token(self) -> Optional[str]:
        """
        Uses the GOOGLE_REFRESH_TOKEN to request a new temporary Access Token.
        This prevents 'Unauthorized' errors during API calls.
        """
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.token_url, data=payload)
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("access_token")
                else:
                    logger.error(f"Google Token Refresh Failed: {response.status_code} - {response.text}")
                    return None
        except Exception as e:
            logger.error(f"Exception during Google token refresh: {str(e)}")
            return None

    async def get_business_reviews(self, account_id: str, location_id: str) -> List[Dict[str, Any]]:
        """
        Fetches all reviews for a specific business location.
        account_id and location_id are required from your Google Business Profile.
        """
        access_token = await self.get_access_token()
        
        if not access_token:
            logger.warning("No access token available. Skipping review fetch.")
            return []

        # Google Business Profile API endpoint for reviews
        url = f"https://mybusiness.googleapis.com/v4/accounts/{account_id}/locations/{location_id}/reviews"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(url, headers=headers)
                
                if response.status_code == 200:
                    reviews_data = response.json()
                    return reviews_data.get("reviews", [])
                elif response.status_code == 404:
                    logger.error(f"Location not found: {location_id}")
                    return []
                else:
                    logger.error(f"Google Reviews API Error: {response.status_code} - {response.text}")
                    return []
        except Exception as e:
            logger.error(f"Exception while fetching Google reviews: {str(e)}")
            return []

# Create a singleton instance for use throughout the application
google_reviews_service = GoogleReviewsService()
