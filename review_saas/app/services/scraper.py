import requests
import json
import os
import asyncio

class ReviewScraper:
    def __init__(self):
        self.api_key = os.getenv("SERPAPI_KEY", "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d")
        self.base_url = "https://serpapi.com/search.json"

    def get_data_id_from_place_id(self, place_id):
        """
        Converts a standard Google place_id to a SerpApi data_id.
        """
        params = {
            "engine": "google_maps",
            "q": place_id,
            "api_key": self.api_key
        }
        try:
            response = requests.get(self.base_url, params=params, timeout=20)
            data = response.json()
            # Try to find the data_id (sometimes called cid or feature_id)
            return data.get("place_results", {}).get("data_id")
        except:
            return None

    def get_reviews_sync(self, identifier, count=20):
        # 1. Check if the identifier looks like a place_id (often starts with ChI)
        # If it is, try to convert it to a data_id first
        active_id = identifier
        if identifier.startswith("ChI"):
            converted_id = self.get_data_id_from_place_id(identifier)
            if converted_id:
                active_id = converted_id

        params = {
            "engine": "google_maps_reviews",
            "data_id": active_id,
            "api_key": self.api_key,
            "num": count,
            "sort_by": "newest"
        }

        try:
            print(f"[*] API Request for: {active_id}")
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            raw_reviews = data.get("reviews", [])
            
            processed = []
            for item in raw_reviews:
                processed.append({
                    "user": item.get("user", {}).get("name", "Anonymous"),
                    "rating": item.get("rating"),
                    "text": item.get("snippet", ""), 
                    "date": item.get("date"),
                    "response_from_owner": item.get("response", {}).get("text", None)
                })
            
            return processed

        except Exception as e:
            print(f"[!] Scraper Error: {e}")
            return []

# --- COMPLETE ASYNC WRAPPER ---

async def fetch_reviews(data_id=None, **kwargs):
    """
    Async Entry Point for ReviewSaaS.
    Handles 'place_id' keyword and 'limit' argument.
    """
    identifier = data_id or kwargs.get('place_id')
    limit = kwargs.get('limit', 20)
    
    if not identifier:
        return []

    scraper = ReviewScraper()
    loop = asyncio.get_event_loop()
    
    # Run the scraping logic in a thread
    reviews = await loop.run_in_executor(None, scraper.get_reviews_sync, identifier, limit)
    
    return reviews
