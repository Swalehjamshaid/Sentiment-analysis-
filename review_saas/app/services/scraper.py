import os
import requests
import json
import csv
import logging
from datetime import datetime

# =========================
# LOGGING CONFIGURATION
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("SerpApiScraper")

class GoogleReviewScraper:
    def __init__(self):
        """
        Initializes the scraper using the SerpApi key from environment variables.
        Fallback to the hardcoded key if the environment variable is not set.
        """
        self.api_key = os.getenv("SERP_API_KEY", "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d")
        self.base_url = "https://serpapi.com/search.json"
        
        if not self.api_key:
            logger.error("❌ SERP_API_KEY is missing. Please set it in your environment or Railway variables.")

    def fetch_reviews(self, query, total_limit=50):
        """
        Complete pipeline to:
        1. Find the place's unique 'data_id' via Google Maps Engine.
        2. Extract reviews using the Google Maps Reviews Engine.
        3. Handle pagination automatically.
        """
        try:
            # STEP 1: Search for the location to get the data_id
            logger.info(f"🔍 Searching for location: {query}")
            search_params = {
                "engine": "google_maps",
                "q": query,
                "api_key": self.api_key
            }
            
            search_response = requests.get(self.base_url, params=search_params, timeout=30)
            search_response.raise_for_status()
            search_results = search_response.json()

            # Extract data_id from place_results or local_results
            place = search_results.get("place_results")
            if not place:
                local_results = search_results.get("local_results", [])
                if not local_results:
                    logger.warning(f"⚠️ No results found for query: {query}")
                    return []
                place = local_results[0]

            data_id = place.get("data_id")
            place_name = place.get("title")
            
            if not data_id:
                logger.error("❌ Could not resolve a data_id for this location.")
                return []

            logger.info(f"✅ Target Found: {place_name} (ID: {data_id})")

            # STEP 2: Fetch reviews with pagination support
            all_reviews = []
            next_page_token = None
            
            while len(all_reviews) < total_limit:
                review_params = {
                    "engine": "google_maps_reviews",
                    "data_id": data_id,
                    "api_key": self.api_key,
                    "next_page_token": next_page_token
                }
                
                logger.info(f"📥 Fetching reviews... (Current count: {len(all_reviews)})")
                res = requests.get(self.base_url, params=review_params, timeout=30)
                res.raise_for_status()
                data = res.json()
                
                batch = data.get("reviews", [])
                if not batch:
                    logger.info("No more reviews available for this location.")
                    break
                
                for r in batch:
                    if len(all_reviews) >= total_limit:
                        break
                    
                    all_reviews.append({
                        "place_name": place_name,
                        "author": r.get("user", {}).get("name"),
                        "rating": r.get("rating"),
                        "text": r.get("snippet", "No comment provided"),
                        "published_at": r.get("date"),
                        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                
                # Update token for next page
                next_page_token = data.get("serpapi_pagination", {}).get("next_page_token")
                if not next_page_token:
                    break

            logger.info(f"🎯 Extraction Complete. Total Reviews: {len(all_reviews)}")
            return all_reviews

        except Exception as e:
            logger.error(f"❌ Scraper failed: {e}")
            return []

    def save_to_csv(self, reviews, filename="google_reviews.csv"):
        """
        Saves the structured review data into a CSV file.
        """
        if not reviews:
            logger.warning("No data found to save.")
            return

        keys = reviews[0].keys()
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                dict_writer = csv.DictWriter(f, fieldnames=keys)
                dict_writer.writeheader()
                dict_writer.writerows(reviews)
            logger.info(f"💾 File successfully saved as: {filename}")
        except Exception as e:
            logger.error(f"❌ Failed to save CSV: {e}")

# =========================
# MAIN EXECUTION
# =========================
if __name__ == "__main__":
    # Initialize the Scraper
    scraper = GoogleReviewScraper()
    
    # Specify the target and limit
    target_query = "Badshahi Mosque Lahore"
    max_reviews = 50
    
    # Run pipeline
    extracted_data = scraper.fetch_reviews(target_query, total_limit=max_reviews)
    
    # Save results
    if extracted_data:
        scraper.save_to_csv(extracted_data)
        
        # Display sample output
        print("\n--- Preview of First Result ---")
        print(json.dumps(extracted_data[0], indent=2))
    else:
        print("No reviews were extracted. Check your API credits or search query.")
