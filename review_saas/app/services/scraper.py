import os
import requests
import json
import logging
from time import sleep
import asyncio

# =========================
# Logging
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# SerpApi Key
# =========================
SERP_API_KEY = os.getenv("SERP_API_KEY")
if not SERP_API_KEY:
    logger.error("SERP_API_KEY is not set! Exiting scraper.")
    raise ValueError("SERP_API_KEY environment variable is missing.")

# =========================
# Scraper Class
# =========================
class ReviewScraper:
    """Robust scraper using SerpApi for Google Reviews."""

    BASE_URL = "https://serpapi.com/search.json"

    def __init__(self, max_retries=3, retry_delay=2):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def fetch_reviews(self, company_name: str, limit=300, place_id: str = None):
        """Fetch reviews using company_name or place_id"""
        logger.info(f"Fetching reviews for {company_name} (limit={limit})")
        params = {
            "engine": "google_maps",
            "q": company_name,
            "google_domain": "google.com",
            "type": "search",
            "hl": "en",
            "api_key": SERP_API_KEY
        }

        if place_id:
            params["type"] = "place"
            params["place_id"] = place_id
            params.pop("q", None)

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.get(self.BASE_URL, params=params, timeout=30)
                data = response.json()

                if "error" in data:
                    logger.error(f"SerpApi error: {data['error']}")
                    return []

                reviews = data.get("reviews", [])

                # If no reviews and no place_id, try first local result
                if not reviews and not place_id:
                    candidate = data.get("local_results", {}).get("places", [])
                    if candidate:
                        first_place_id = candidate[0].get("place_id")
                        if first_place_id:
                            logger.info(f"No reviews found. Retrying with place_id: {first_place_id}")
                            return self.fetch_reviews(company_name, limit=limit, place_id=first_place_id)

                if reviews:
                    return reviews[:limit]

                logger.warning(f"No reviews found on attempt {attempt} for {company_name}")
                if attempt < self.max_retries:
                    sleep(self.retry_delay)

            except Exception as e:
                logger.error(f"Error fetching reviews (attempt {attempt}): {e}")
                if attempt < self.max_retries:
                    sleep(self.retry_delay)
                else:
                    return []

        return []

# =========================
# Module-level scraper
# =========================
scraper_instance = ReviewScraper()

# =========================
# Async wrapper for FastAPI
# =========================
async def fetch_reviews(company_name=None, name=None, limit=300, place_id=None):
    """
    Async wrapper compatible with FastAPI routes.
    Accepts:
        - company_name (preferred)
        - name (fallback)
        - limit
        - place_id
    """
    target_name = company_name or name
    if not target_name:
        raise ValueError("Either company_name or name must be provided to fetch reviews.")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, scraper_instance.fetch_reviews, target_name, limit, place_id)


# =========================
# Standalone test
# =========================
if __name__ == "__main__":
    companies = ["Villa The Grand Buffet", "Bahria Town"]
    for company in companies:
        reviews = asyncio.run(fetch_reviews(name=company))
        if not reviews:
            logger.info(f"No reviews returned for {company}")
        else:
            logger.info(f"Fetched {len(reviews)} reviews for {company}")
            with open(f"{company.replace(' ', '_')}_reviews.json", "w", encoding="utf-8") as f:
                json.dump(reviews, f, ensure_ascii=False, indent=2)
