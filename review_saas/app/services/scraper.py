import requests
import json
import os
import asyncio

class ReviewScraper:
    """
    Complete Scraper for ReviewSaaS using SerpApi.
    Optimized for Railway to avoid memory issues and handle asynchronous calls.
    """
    
    def __init__(self):
        # API Key from your SerpApi dashboard
        self.api_key = os.getenv("SERPAPI_KEY", "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d")
        self.base_url = "https://serpapi.com/search.json"

    def get_reviews_sync(self, identifier, count=20):
        """
        Synchronous logic to fetch reviews. 
        SerpApi handles proxies and browser emulation internally.
        """
        params = {
            "engine": "google_maps_reviews",
            "data_id": identifier,
            "api_key": self.api_key,
            "num": count,
            "sort_by": "newest"
        }

        try:
            print(f"[*] API Request for ID: {identifier} (Limit: {count})")
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            raw_reviews = data.get("reviews", [])
            
            processed = []
            for item in raw_reviews:
                processed.append({
                    "user": item.get("user", {}).get("name", "Anonymous"),
                    "rating": item.get("rating"),
                    "text": item.get("snippet", ""), # 'text' field used by your sentiment logic
                    "date": item.get("date"),
                    "response_from_owner": item.get("response", {}).get("text", None)
                })
            
            print(f"[+] Successfully retrieved {len(processed)} reviews.")
            return processed

        except Exception as e:
            print(f"[!] Scraper Error: {e}")
            return []

# --- CRITICAL: Complete Async Wrapper for main.py & routes/reviews.py ---

async def fetch_reviews(data_id=None, **kwargs):
    """
    Fixed Async Entry Point.
    Resolves: TypeError: object list can't be used in 'await' expression
    Resolves: TypeError: fetch_reviews() got an unexpected keyword argument 'place_id'
    """
    # 1. Capture the identifier from either data_id or place_id
    identifier = data_id or kwargs.get('place_id')
    
    # 2. Capture the 'limit' argument passed by app.reviews
    limit = kwargs.get('limit', 20)
    
    if not identifier:
        print("[!] fetch_reviews Error: No identifier (place_id/data_id) provided.")
        return []

    scraper = ReviewScraper()

    # 3. Use the event loop to run the synchronous request in a thread.
    # This makes the function 'awaitable' and prevents blocking the FastAPI event loop.
    loop = asyncio.get_event_loop()
    try:
        # We pass the limit (300) to the sync function
        reviews = await loop.run_in_executor(None, scraper.get_reviews_sync, identifier, limit)
        return reviews
    except Exception as e:
        print(f"[!] Async execution error: {e}")
        return []

# --- Standard Utility for ReviewSaaS ---

def save_to_file(data, filename="scraped_reviews.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- Local Test Logic ---

if __name__ == "__main__":
    # Test mimicking the FastAPI call style
    test_id = "0x3919016e789d2c5f:0x39223700b0808b2d"
    
    # To test async locally:
    async def test():
        print("[*] Running local async test...")
        results = await fetch_reviews(place_id=test_id, limit=5)
        print(f"[*] Test results: {len(results)} reviews found.")
    
    asyncio.run(test())
