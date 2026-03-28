import requests
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("ReviewScraper")

class SerpApiReviewScraper:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://serpapi.com/search.json"

    def get_reviews_by_query(self, query, review_limit=20):
        """
        Full pipeline: Find the place, then extract its reviews.
        """
        try:
            # Step 1: Find the place to get the unique data_id
            logger.info(f"Searching for place: {query}")
            search_params = {
                "engine": "google_maps",
                "q": query,
                "api_key": self.api_key
            }
            
            search_res = requests.get(self.base_url, params=search_params)
            search_res.raise_for_status()
            search_data = search_res.json()

            # Identify the data_id (required for the reviews engine)
            place_results = search_data.get("place_results")
            if not place_results:
                logger.error("No specific place found for this query.")
                return []
            
            data_id = place_results.get("data_id")
            logger.info(f"Found Place: {place_results.get('title')} (ID: {data_id})")

            # Step 2: Fetch the reviews using the data_id
            logger.info(f"Fetching up to {review_limit} reviews...")
            review_params = {
                "engine": "google_maps_reviews",
                "data_id": data_id,
                "api_key": self.api_key,
                "num": review_limit
            }
            
            review_res = requests.get(self.base_url, params=review_params)
            review_res.raise_for_status()
            reviews = review_res.json().get("reviews", [])

            return self._format_results(reviews)

        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            return []

    def _format_results(self, reviews):
        """Clean and structure the raw API response."""
        extracted_data = []
        for r in reviews:
            extracted_data.append({
                "user": r.get("user", {}).get("name"),
                "rating": r.get("rating"),
                "date": r.get("date"),
                "snippet": r.get("snippet", "No text provided"),
                "likes": r.get("likes", 0)
            })
        return extracted_data

# --- RUNNING THE SCRAPER ---
# Note: Ensure you have regenerated your key if you haven't already.
MY_API_KEY = "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d"

scraper = SerpApiReviewScraper(MY_API_KEY)
results = scraper.get_reviews_by_query("The British Museum", review_limit=10)

# Output results
if results:
    print(json.dumps(results, indent=2))
else:
    print("No reviews found.")
