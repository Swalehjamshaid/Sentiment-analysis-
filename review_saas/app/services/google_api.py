# review_saas/app/services/google_api.py

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ---------------------------
# Google API Service Wrapper
# ---------------------------
class GoogleAPIService:
    def __init__(self, credentials_json_path: str):
        self.credentials = service_account.Credentials.from_service_account_file(
            credentials_json_path,
            scopes=["https://www.googleapis.com/auth/business.manage"]
        )
        self.service = build("mybusiness", "v4", credentials=self.credentials)

    def get_reviews(self, account_id: str, location_id: str):
        """
        Fetch Google Reviews for a specific location.
        """
        reviews = []
        try:
            response = self.service.accounts().locations().reviews().list(
                parent=f"accounts/{account_id}/locations/{location_id}"
            ).execute()
            reviews = response.get("reviews", [])
        except Exception as e:
            print("Error fetching Google Reviews:", e)
        return reviews

# ---------------------------
# Factory Function
# ---------------------------
def get_google_api_service(credentials_json_path: str = "/app/credentials.json") -> GoogleAPIService:
    return GoogleAPIService(credentials_json_path)
