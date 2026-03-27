import requests
import json
import os

# --- Scraper.py for ReviewSaaS ---

class ReviewScraper:
    """
    Complete Scraper for ReviewSaaS using SerpApi.
    This replaces the Playwright/Outscraper logic for better stability on Railway.
    """
    
    def __init__(self, api_key=None):
        # Fallback to the key from your dashboard if not in environment variables
        self.api_key = api_key or "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d"
        self.base_url = "https://serpapi.com/search.json"

    def get_google_maps_reviews(self, data_id, count=10):
        """
        Fetches structured reviews from Google Maps.
        :param data_id: The unique ID for the location (found in Maps URLs).
        :param count: Number of reviews to attempt to fetch.
        """
        params = {
            "engine": "google_maps_reviews",
            "data_id": data_id,
            "api_key": self.api_key,
            "num": count,
            "sort_by": "newest"
        }

        try:
            print(f"[*] Fetching reviews for data_id: {data_id}...")
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            raw_reviews = data.get("reviews", [])
            
            processed_reviews = []
            for item in raw_reviews:
                review_data = {
                    "user": item.get("user", {}).get("name", "Anonymous"),
                    "rating": item.get("rating"),
                    "snippet": item.get("snippet", ""),
                    "date": item.get("date"),
                    "response_from_owner": item.get("response", {}).get("text", None)
                }
                processed_reviews.append(review_data)
            
            return processed_reviews

        except requests.exceptions.RequestException as e:
            print(f"[!] API Error: {e}")
            return []

    def save_to_json(self, reviews, filename="reviews_output.json"):
        """Saves the scraped data for ReviewSaaS processing."""
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(reviews, f, indent=4, ensure_ascii=False)
            print(f"[+] Successfully saved {len(reviews)} reviews to {filename}")
        except Exception as e:
            print(f"[!] Save Error: {e}")

# --- Execution Logic ---

if __name__ == "__main__":
    # Initialize the scraper
    scraper = ReviewScraper()
    
    # Example: Google Maps data_id for a business
    # You can extract this ID from the 'ludocid' or 'fid' in Google URLs
    target_data_id = "0x3919016e789d2c5f:0x39223700b0808b2d" 
    
    # 1. Scrape
    reviews_list = scraper.get_google_maps_reviews(target_data_id, count=20)
    
    # 2. Display / Save
    if reviews_list:
        for idx, r in enumerate(reviews_list, 1):
            print(f"{idx}. [{r['rating']} Stars] {r['user']}: {r['snippet'][:50]}...")
        
        scraper.save_to_json(reviews_list)
    else:
        print("[-] No reviews found or error occurred.")
