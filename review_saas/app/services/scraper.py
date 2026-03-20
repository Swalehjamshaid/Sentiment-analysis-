import httpx
import json
import logging
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

# Set up logging to help track errors in Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FastGoogleScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
            "Accept": "*/*",
            "Referer": "https://www.google.com/",
        }

    async def get_reviews(self, data_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetches and parses reviews from Google Maps for a specific data_id.
        """
        # Google Maps review endpoint
        url = "https://www.google.com/maps/preview/review/listentitiesreviews"
        
        # 'pb' is the internal Google parameter for pagination and data identification
        pb = f"!1m1!1s{data_id}!2i0!3i{limit}!4m5!4b1!5b1!6b1!7b1!5e1"
        params = {
            "authuser": "0",
            "hl": "en",
            "gl": "us",
            "pb": pb
        }

        reviews_list = []

        async with httpx.AsyncClient(headers=self.headers, timeout=30.0, follow_redirects=True) as client:
            try:
                response = await client.get(url, params=params)
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch reviews. Status: {response.status_code}")
                    return []

                # Google's JSON response starts with a security prefix: )]}'
                content = response.text.lstrip(")]}'\n")
                data = json.loads(content)

                # Navigate the nested Google JSON structure
                # The reviews are typically found in the second element of the data array
                raw_reviews = data[2] if len(data) > 2 else []

                for r in raw_reviews:
                    try:
                        review_data = {
                            "review_id": r[0],
                            "rating": r[4],
                            "text": r[3] if r[3] else "",
                            "author_title": r[1][4][0][4] if r[1] else "Anonymous",
                            "timestamp": r[27], # Unix timestamp in milliseconds
                            "datetime_utc": datetime.fromtimestamp(r[27]/1000, tz=timezone.utc).isoformat()
                        }
                        reviews_list.append(review_data)
                    except (IndexError, TypeError, KeyError) as e:
                        continue

                logger.info(f"Successfully scraped {len(reviews_list)} reviews for {data_id}")
                return reviews_list

            except Exception as e:
                logger.error(f"Critical error during scraping: {str(e)}")
                return []

# --- CRITICAL FIX FOR YOUR IMPORT ERROR ---
async def fetch_reviews(data_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Entry point used by app.routes.reviews.
    This fixes the 'ImportError: cannot import name fetch_reviews'
    """
    scraper = FastGoogleScraper()
    return await scraper.get_reviews(data_id, limit)
