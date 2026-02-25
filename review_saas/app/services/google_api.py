# review_saas/app/services/google_api.py

import os
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger("review_saas")

# ---------------------------
# Google API Service Wrapper
# ---------------------------
class GoogleAPIService:
    def __init__(self, credentials_json_path: str):
        self.service = None
        self.credentials = None
        
        # Check if the credentials file actually exists before trying to load it
        if credentials_json_path and os.path.exists(credentials_json_path):
            try:
                self.credentials = service_account.Credentials.from_service_account_file(
                    credentials_json_path,
                    scopes=["https://www.googleapis.com/auth/business.manage"]
                )
                self.service = build("mybusinessbusinesscalls", "v1", credentials=self.credentials)
                logger.info("Google Business API initialized with Service Account.")
            except Exception as e:
                logger.error("Failed to initialize Google Service Account: %s", e)
        else:
            # Fallback: Use API Key if available for public data, 
            # though MyBusiness usually requires OAuth/Service Account.
            logger.warning(f"Google credentials file not found at {credentials_json_path}. API will run in limited mode.")
            self.api_key = os.getenv("GOOGLE_BUSINESS_API_KEY")

    def get_reviews(self, account_id: str, location_id: str):
        """
        Fetch Google Reviews for a specific location.
        """
        if not self.service:
            logger.error("Google Business Service not initialized. Cannot fetch reviews.")
            return []

        reviews = []
        try:
            # Note: The MyBusiness API structure often changes; check the specific version documentation
            parent = f"accounts/{account_id}/locations/{location_id}"
            response = self.service.accounts().locations().reviews().list(
                parent=parent
            ).execute()
            reviews = response.get("reviews", [])
        except Exception as e:
            logger.error("Error fetching Google Reviews: %s", e)
        return reviews

# ---------------------------
# Factory Function
# ---------------------------
def get_google_api_service(credentials_json_path: str = None) -> GoogleAPIService:
    # Use environment variable for path or default to a safe None
    path = credentials_json_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/app/credentials.json")
    return GoogleAPIService(path)
