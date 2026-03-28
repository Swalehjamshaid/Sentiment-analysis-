import os
import requests
import json
import logging
from time import sleep

# =========================
# Logging
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# SerpApi Key
# =========================
SERP_API_KEY = os.getenv("SERP_API_KEY")  # Make sure this is set in Railway env

if not SERP_API_KEY:
    logger.error("SERP_API_KEY is not set! Exiting scraper.")
    raise ValueError("SERP_API_KEY environment variable is missing.")


class ReviewScraper:
    """
    Scraper using SerpApi for Google Reviews.
    Handles empty results and retries.
    """

    BASE_URL = "https://serpapi.com/search.json"

    def __init__(self, max_retries=3, retry_delay=2):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def fetch_reviews(self, company_name: str, limit=300):
        """
        Fetch reviews for a given company name using SerpApi
        """
        logger.info(f"Fetching reviews for {company_name} (limit={limit})")

        params = {
            "engine": "google_maps",
            "q": company_name,
            "google_domain": "google.com",
            "type": "search",
            "hl": "en",
            "api_key": SERP_API_KEY
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.get(self.BASE_URL, params=params, timeout=30)
                data = response.json()

                # Log full raw response for debugging
                logger.info(f"SerpApi Raw Response: {json.dumps(data, indent=2)[:1000]}...")

                reviews = data.get("reviews", [])

                if not reviews:
                    logger.warning(f"No reviews found on attempt {attempt} for {company_name}")
                    if attempt < self.max_retries:
                        logger.info(f"Retrying in {self.retry_delay} seconds...")
                        sleep(self.retry_delay)
                    continue

                # Limit reviews if needed
                return reviews[:limit]

            except Exception as e:
                logger.error(f"Error fetching reviews (attempt {attempt}): {e}")
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.retry_delay} seconds...")
                    sleep(self.retry_delay)
                else:
                    return []

        return []


# =========================
# Example usage
# =========================
if __name__ == "__main__":
    scraper = ReviewScraper()

    companies = ["Villa The Grand Buffet", "Bahria Town"]
    for company in companies:
        reviews = scraper.fetch_reviews(company)
        if not reviews:
            logger.info(f"ℹ️ No reviews returned for {company}")
        else:
            logger.info(f"✅ Fetched {len(reviews)} reviews for {company}")
            # Save to JSON file
            with open(f"{company.replace(' ', '_')}_reviews.json", "w", encoding="utf-8") as f:
                json.dump(reviews, f, ensure_ascii=False, indent=2)
