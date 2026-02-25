# review_saas/app/services/google_api.py
import os
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger("review_saas")

class GoogleAPIService:
    def __init__(self, credentials_json_path: str):
        self.service = None
        # FIX: Only attempt to load if the file actually exists
        if credentials_json_path and os.path.exists(credentials_json_path):
            try:
                self.credentials = service_account.Credentials.from_service_account_file(
                    credentials_json_path,
                    scopes=["https://www.googleapis.com/auth/business.manage"]
                )
                self.service = build("mybusinessbusinesscalls", "v1", credentials=self.credentials)
                logger.info("Google API initialized successfully.")
            except Exception as e:
                logger.error(f"Google API init failed: {e}")
        else:
            logger.warning(f"Credentials not found at {credentials_json_path}. Running in limited mode.")

    def get_reviews(self, account_id: str, location_id: str):
        if not self.service:
            return [] # Return empty list instead of crashing
        try:
            return self.service.accounts().locations().reviews().list(
                parent=f"accounts/{account_id}/locations/{location_id}"
            ).execute().get("reviews", [])
        except Exception:
            return []

def get_google_api_service(credentials_json_path: str = None) -> GoogleAPIService:
    path = credentials_json_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/app/credentials.json")
    return GoogleAPIService(path)
