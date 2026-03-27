import os
import requests
import logging
import asyncio
from datetime import datetime

# =================================================================
# CONFIGURATION & LOGGING
# =================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ReviewSaaS.Outscraper")

# Ensure this variable is set in Railway Variables tab:
# Name: OUTSCRAPER_API_KEY
# Value: QUxMIFIFPVVlgkFTRSBBUKUgQkVMT05HIFRP
API_KEY = os.getenv("OUTSCRAPER_API_KEY")

# =================================================================
# CORE SCRAPER FUNCTION
# =================================================================
async def fetch_reviews(place_id: str, limit: int = 5):
    """
    Outscraper API Implementation:
    - No Chromium browser required (saves 500MB+ RAM on Railway).
    - Fetches clean JSON directly from Outscraper's specialized Google Maps engine.
    - Highly reliable for locations like E11EVEN MIAMI or Salt'n Pepper.
    """
    logger.info(f"🚀 [Railway] Starting Outscraper API fetch for: {place_id}")

    if not API_KEY:
        logger.error("❌ OUTSCRAPER_API_KEY missing in Railway Variables!")
        return []

    # Outscraper Maps Reviews V3 Endpoint
    endpoint = "https://api.app.outscraper.com/maps/reviews-v3"
    
    # We pass the query (place_id) and the limit (5)
    params = {
        "query": place_id,
        "reviewsLimit": limit,
        "async": "false",
        "language": "en"
    }

    headers = {
        "X-API-KEY": API_KEY
    }

    try:
        # Using a thread pool to handle the synchronous requests call in an async function
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.get(endpoint, params=params, headers=headers, timeout=120)
        )
        
        if response.status_code != 200:
            logger.error(f"❌ Outscraper API Error: {response.status_code} - {response.text}")
            return []

        data = response.json()
        
        # Check if data structure is as expected
        if not data.get("data") or len(data["data"]) == 0:
            logger.warning(f"⚠️ No data returned from Outscraper for: {place_id}")
            return []

        # Outscraper nests reviews inside the first element of the data list
        raw_reviews = data["data"][0].get("reviews_data", [])
        reviews_data = []

        for r in raw_reviews[:limit]:
            reviews_data.append({
                "review_id": r.get("review_id"),
                "author_name": r.get("author_title"),
                "rating": r.get("review_rating"),
                "text": r.get("review_text") or "No text content provided.",
                "relative_date": r.get("review_datetime_utc"),
                "scraped_at": datetime.utcnow().isoformat()
            })
            logger.info(f"✨ Captured review from: {r.get('author_title')}")

        logger.info(f"✅ Scraping Complete. Total Reviews: {len(reviews_data)}")
        return reviews_data

    except Exception as e:
        logger.error(f"❌ Critical Failure in Outscraper Logic: {str(e)}")
        return []

# Compatibility Aliases for your Main App (app.reviews)
scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
