import requests
import json
import os
import asyncio

class ReviewScraper:
    """
    Robust Scraper for ReviewSaaS. 
    Handles Name-to-ID conversion to prevent '0 reviews' errors.
    """
    def __init__(self):
        # Your SerpApi Key from the dashboard
        self.api_key = os.getenv("SERPAPI_KEY", "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d")
        self.base_url = "https://serpapi.com/search.json"

    def resolve_to_data_id(self, query):
        """
        Converts a name like 'Salt'n Pepper Village Lahore' into a SerpApi data_id.
        """
        search_params = {
            "engine": "google_maps",
            "q": query,
            "api_key": self.api_key,
            "type": "search"
        }
        try:
            print(f"[*] Resolving ID for: {query}")
            response = requests.get(self.base_url, params=search_params, timeout=20)
            data = response.json()
            
            # 1. Try direct place results
            if "place_results" in data and data["place_results"].get("data_id"):
                return data["place_results"].get("data_id")
            
            # 2. Try first result in the local list (common for restaurants)
            local_results = data.get("local_results", [])
            if local_results:
                return local_results[0].get("data_id")
                
            return None
        except Exception as e:
            print(f"[!] ID Resolution Error: {e}")
            return None

    def get_reviews_sync(self, identifier, count=20):
        # Step 1: Ensure we have a valid data_id (starts with 0x)
        active_id = identifier
        if not (str(identifier).startswith("0x") and ":" in str(identifier)):
            active_id = self.resolve_to_data_id(identifier)
            if not active_id:
                print(f"[!] Failure: Could not find a specific map location for '{identifier}'")
                return []
            print(f"[+] Resolved to Data ID: {active_id}")

        # Step 2: Fetch the actual reviews
        params = {
            "engine": "google_maps_reviews",
            "data_id": active_id,
            "api_key": self.api_key,
            "num": count,
            "sort_by": "newest"
        }

        try:
            res = requests.get(self.base_url, params=params, timeout=30)
            res.raise_for_status()
            data = res.json()
            
            raw_reviews = data.get("reviews", [])
            processed = []
            
            for item in raw_reviews:
                processed.append({
                    "user": item.get("user", {}).get("name", "Anonymous"),
                    "rating": item.get("rating"),
                    "text": item.get("snippet") or item.get("text") or "", 
                    "date": item.get("date"),
                    "response_from_owner": item.get("response", {}).get("text", None)
                })
            
            print(f"[+] Success: Found {len(processed)} reviews for {identifier}")
            return processed

        except Exception as e:
            print(f"[!] Fetch Error: {e}")
            return []

# --- ASYNC WRAPPER FOR FASTAPI ---

async def fetch_reviews(data_id=None, **kwargs):
    """
    Entry point for your 'app.reviews' router.
    Handles 'place_id', 'limit', and keyword arguments.
    """
    # Priority: data_id > place_id > query
    identifier = data_id or kwargs.get('place_id') or kwargs.get('query')
    limit = kwargs.get('limit', 20)
    
    if not identifier:
        return []

    scraper = ReviewScraper()
    loop = asyncio.get_event_loop()
    
    # Run in a thread to keep the FastAPI server responsive
    return await loop.run_in_executor(None, scraper.get_reviews_sync, identifier, limit)
