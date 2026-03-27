import requests
import json
import os

class ReviewScraper:
    def __init__(self):
        # Your SerpApi Key
        self.api_key = os.getenv("SERPAPI_KEY", "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d")
        self.base_url = "https://serpapi.com/search.json"

    def get_reviews(self, identifier, count=20):
        """
        SerpApi can use 'data_id' or 'place_id' depending on the engine.
        We will attempt to use the provided identifier as the data_id for Google Maps.
        """
        params = {
            "engine": "google_maps_reviews",
            "api_key": self.api_key,
            "num": count,
            "sort_by": "newest"
        }
        
        # Determine if we should use place_id or data_id parameter
        # SerpApi Google Maps Reviews engine specifically prefers 'data_id'
        params["data_id"] = identifier

        try:
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
                    "date": item.get("date")
                })
            return processed

        except Exception as e:
            print(f"Scraper Error for {identifier}: {e}")
            return []

# --- FIXED WRAPPER ---

def fetch_reviews(data_id=None, **kwargs):
    """
    Fixed to handle 'place_id' keyword argument from app.reviews.
    """
    # If main.py passes place_id=..., we grab it here
    identifier = data_id or kwargs.get('place_id')
    
    if not identifier:
        print("[!] No identifier (data_id or place_id) provided to fetch_reviews")
        return []
        
    scraper = ReviewScraper()
    return scraper.get_reviews(identifier)
