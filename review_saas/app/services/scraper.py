import requests
import json
import os
import asyncio

class ReviewScraper:
    def __init__(self):
        self.api_key = os.getenv("SERPAPI_KEY", "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d")
        self.base_url = "https://serpapi.com/search.json"

    def get_data_id_by_search(self, query):
        """
        If we only have a name (like 'McDonald's'), this finds the specific data_id.
        """
        search_params = {
            "engine": "google_maps",
            "q": query,
            "api_key": self.api_key
        }
        try:
            print(f"[*] Searching for data_id for: {query}")
            response = requests.get(self.base_url, params=search_params, timeout=20)
            data = response.json()
            
            # Extract data_id from the first result
            place_results = data.get("place_results")
            if place_results:
                return place_results.get("data_id")
            
            # Fallback to local_results if place_results is empty
            local_results = data.get("local_results", [])
            if local_results:
                return local_results[0].get("data_id")
                
            return None
        except Exception as e:
            print(f"[!] Search Error: {e}")
            return None

    def get_reviews_sync(self, identifier, count=20):
        # 1. Check if the identifier is a name (no '0x' prefix) or a place_id
        # If it doesn't look like a SerpApi data_id, we search for it.
        active_id = identifier
        if not (identifier.startswith("0x") and ":" in identifier):
            found_id = self.get_data_id_by_search(identifier)
            if found_id:
                active_id = found_id
            else:
                print(f"[!] Could not find a specific data_id for: {identifier}")
                return []

        # 2. Fetch the reviews using the confirmed data_id
        params = {
            "engine": "google_maps_reviews",
            "data_id": active_id,
            "api_key": self.api_key,
            "num": count,
            "sort_by": "newest"
        }

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
            print(f"[!] Scraper Error: {e}")
            return []

# --- ASYNC WRAPPER ---

async def fetch_reviews(data_id=None, **kwargs):
    identifier = data_id or kwargs.get('place_id')
    limit = kwargs.get('limit', 20)
    
    if not identifier:
        return []

    scraper = ReviewScraper()
    loop = asyncio.get_event_loop()
    reviews = await loop.run_in_executor(None, scraper.get_reviews_sync, identifier, limit)
    return reviews
