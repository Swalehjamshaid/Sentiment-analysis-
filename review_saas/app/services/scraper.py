import os
import json
import asyncio
import logging
from typing import List

import requests
from dotenv import load_dotenv

# =========================
# LOAD ENV VARIABLES
# =========================
load_dotenv()
SERP_API_KEY = os.getenv("SERP_API_KEY")

# =========================
# LOGGING CONFIG
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ReviewScraper")

# =========================
# SCRAPER CLASS
# =========================
class ReviewScraper:
    """
    Robust scraper for Google Reviews via SerpAPI.
    Handles JSON parsing safely and logs errors without breaking.
    """

    def __init__(self, api_key: str = SERP_API_KEY):
        if not api_key:
            raise ValueError("SERP_API_KEY is missing in your environment variables.")
        self.api_key = api_key
        self.base_url = "https://serpapi.com/search.json"

    def fetch_reviews(self, place_id: str) -> List[dict]:
        """
        Fetch reviews for a given Google Place ID using SerpAPI.
        Returns a list of review dicts.
        """
        params = {
            "engine": "google_reviews",
            "place_id": place_id,
            "api_key": self.api_key
        }

        try:
            response = requests.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()

            try:
                data = response.json()
            except json.JSONDecodeError:
                logger.error("Failed to parse JSON response: %s", response.text)
                return []

            # Safely access the reviews key
            reviews = data.get("reviews", [])
            if not isinstance(reviews, list):
                logger.warning("Expected 'reviews' to be a list, got: %s", type(reviews))
                return []

            return reviews

        except requests.RequestException as e:
            logger.error("Request failed: %s", e)
            return []

    async def ingest_reviews(self, place_name: str, place_id: str):
        """
        Async ingestion of reviews for a specific place.
        Logs any errors and skips invalid items.
        """
        logger.info(f"🚀 Initializing Scraper for: {place_name}")
        reviews = self.fetch_reviews(place_id)

        if not reviews:
            logger.error(f"❌ No reviews fetched for {place_name}")
            return

        for item in reviews:
            if not isinstance(item, dict):
                logger.warning(f"Skipping invalid item (not a dict): {item}")
                continue

            review_id = item.get("review_id")
            if not review_id:
                logger.warning(f"Skipping item with missing review_id: {item}")
                continue

            # Example processing: log review_id (you can save to DB/ORM)
            logger.info(f"Processing review_id: {review_id}")


# =========================
# EXAMPLE USAGE
# =========================
if __name__ == "__main__":
    scraper = ReviewScraper()

    # Replace with your real Google Place ID
    place_id_example = "ChIJN1t_tDeuEmsRUsoyG83frY4"
    place_name_example = "Salt'n Pepper Village Lahore"

    asyncio.run(scraper.ingest_reviews(place_name_example, place_id_example))
