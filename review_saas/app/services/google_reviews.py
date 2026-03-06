# File: review_saas/app/services/google_reviews.py
import httpx
import logging
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

class GoogleReviewsService:
    def __init__(self):
        # Ensure OUTSCAPTER_KEY is defined in your settings.py
        self.api_key = settings.OUTSCAPTER_KEY 
        self.base_url = "https://api.outscapter.com/v1/reviews/google-maps"

    async def fetch_reviews(self, queries: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetches reviews from Outscapter. 
        Outscapter often uses 'queries' (the Google Maps URL or Place Name) 
        to identify the location.
        """
        all_reviews = []
        
        # Outscapter uses the API key in the 'X-API-KEY' or 'Authorization' header
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Outscapter parameters often include 'queries' and 'limit'
        params = {
            "queries": [queries],  # Outscapter expects an array of queries
            "limit": limit,
            "sort": "newest"       # Common parameter for Outscapter
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                # Outscapter's modern endpoints often use POST for query arrays
                response = await client.post(self.base_url, headers=headers, json=params)
                
                if response.status_code != 200:
                    logger.error(f"Outscapter API Error: {response.status_code} - {response.text}")
                    return []

                response_data = response.json()
                
                # Outscapter's typical structure: {"data": [{"reviews": [...]}]}
                # We extract and flatten the results
                results = response_data.get("data", [])
                
                for result in results:
                    reviews = result.get("reviews_data", [])
                    # Map Outscapter fields to standard Google API fields if necessary
                    for rev in reviews:
                        mapped_review = {
                            "reviewId": rev.get("review_id"),
                            "reviewer": {"displayName": rev.get("author_title")},
                            "starRating": rev.get("rating"),
                            "comment": rev.get("review_text"),
                            "createTime": rev.get("review_datetime_utc"),
                            "reply": rev.get("owner_answer")
                        }
                        all_reviews.append(mapped_review)

            except Exception as e:
                logger.error(f"Outscapter request failed: {str(e)}")
                return []

        logger.info(f"Successfully fetched {len(all_reviews)} reviews from Outscapter.")
        return all_reviews

# Initialize Service Instance
google_reviews_service = GoogleReviewsService()

# --- HELPER FUNCTIONS ---

async def fetch_place_details(query: str) -> Dict[str, Any]:
    """
    Fetches business details using Outscapter search.
    """
    url = "https://api.outscapter.com/v1/search/google-maps"
    headers = {"Authorization": f"Bearer {settings.OUTSCAPTER_KEY}"}
    payload = {"queries": [query], "limit": 1}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                data = response.json().get("data", [])
                return data[0] if data else {}
            return {}
        except Exception as e:
            logger.error(f"Outscapter detail fetch failed: {str(e)}")
            return {}

async def ingest_company_reviews(query: str):
    """
    Simplified ingestion function for routes.
    'query' can be the Google Maps CID, Place ID, or Search Term.
    """
    return await google_reviews_service.fetch_reviews(query)
