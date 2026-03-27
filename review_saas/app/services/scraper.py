import requests
import json
import os

class ReviewScraper:
    """
    Core Scraper class using SerpApi for high reliability on Railway.
    """
    def __init__(self):
        # Your SerpApi Key from the dashboard screenshot
        self.api_key = os.getenv("SERPAPI_KEY", "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d")
        self.base_url = "https://serpapi.com/search.json"

    def get_reviews(self, data_id, count=20):
        params = {
            "engine": "google_maps_reviews",
            "data_id": data_id,
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
                    "text": item.get("snippet", ""), # 'text' is often expected by sentiment models
                    "date": item.get("date")
                })
            return processed

        except Exception as e:
            print(f"Scraper Error: {e}")
            return []

# --- CRITICAL: Wrapper function for your main.py import ---

def fetch_reviews(data_id):
    """
    This function matches the import in your app/main.py:
    from app.services.scraper import fetch_reviews
    """
    scraper = ReviewScraper()
    return scraper.get_reviews(data_id)

# ---------------------------------------------------------

if __name__ == "__main__":
    # Local testing logic
    test_id = "0x3919016e789d2c5f:0x39223700b0808b2d"
    results = fetch_reviews(test_id)
    print(f"Found {len(results)} reviews.")
