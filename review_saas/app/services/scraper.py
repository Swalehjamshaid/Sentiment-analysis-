import os
import requests
import logging
from datetime import datetime

# =================================================================
# CONFIGURATION & LOGGING
# =================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ReviewSaaS.Outscraper")

# Pulling the key you just added to Railway
API_KEY = os.getenv("OUTSCRAPER_API_KEY")

# =================================================================
# CORE SCRAPER FUNCTION
# =================================================================
async def fetch_reviews(place_id: str, limit: int = 5):
    """
    Outscraper API Version:
    - No Browser needed (Saves Railway RAM)
    - Direct JSON response
    - Extremely high success rate for Google Maps
    """
    logger.info(f"🚀 [Railway] Starting Outscraper API for: {place_id}")

    if not API_KEY:
        logger.error("❌ OUTSCRAPER_API_KEY missing in Railway Variables!")
        return []

    # Outscraper uses a simple GET request
    # Documentation: https://app.outscraper.com/api-docs
    endpoint = "https://api.app.outscraper.com/maps/reviews-v3"
    
    params = {
        "query": place_id,     # Your Place ID (e.g., ChIJDVYKpFEEGTkRp_XASXZ21Tc)
        "reviewsLimit": limit, # Set to 5 as requested
        "async": "false",      # Wait for the result immediately
        "language": "en"       # Ensure reviews are in English
    }

    headers = {
        "X-API-KEY": API_KEY
    }

    try:
        # We use a standard requests call (synchronous is fine here as it's a direct API)
        response = requests.get(endpoint, params=params, headers=headers, timeout=120)
        
        if response.status_code != 200:
            logger.error(f"❌ Outscraper Error: {response.status_code} - {response.text}")
            return []

        data = response.json()
        
        # Outscraper returns an array of results (one for each query)
        if not data.get("data") or len(data["data"]) == 0:
            logger.warning("⚠️ No reviews found for this Place ID.")
            return []

        raw_reviews = data["data"][0].get("reviews_data", [])
        reviews_data = []

        for r in raw_reviews[:limit]:
            reviews_data.append({
                "review_id": r.get("review_id"),
                "author_name": r.get("author_title"),
                "rating": r.get("review_rating"),
                "text": r.get("review_text") or "No text content",
                "scraped_at": datetime.utcnow().isoformat()
            })
            logger.info(f"✨ Captured Review from {r.get('author_title')}")

        logger.info(f"✅ Scraping Complete. Total Found: {len(reviews_data)}")
        return reviews_data

    except Exception as e:
        logger.error(f"❌ Outscraper Connection Failure: {str(e)}")
        return []

# Compatibility Aliases for your app
scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
