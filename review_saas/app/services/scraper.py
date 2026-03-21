import httpx
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

# Set up logging to track scraping status in Railway Deploy Logs
logger = logging.getLogger(__name__)

class FastGoogleScraper:
    def __init__(self):
        # Mobile headers help prevent being blocked by Google
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
            "Accept": "*/*",
            "Referer": "https://www.google.com/",
        }

    async def get_reviews(self, data_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Main logic to fetch and parse reviews from Google's internal API.
        """
        # Google Maps internal review endpoint
        url = "https://www.google.com/maps/preview/review/listentitiesreviews"
        
        # 'pb' is the parameter string containing the data_id and result limit
        pb = f"!1m1!1s{data_id}!2i0!3i{limit}!4m5!4b1!5b1!6b1!7b1!5e1"
        params = {
            "authuser": "0",
            "hl": "en",
            "gl": "us",
            "pb": pb
        }

        reviews_list = []

        async with httpx.AsyncClient(headers=self.headers, timeout=60.0, follow_redirects=True) as client:
            try:
                response = await client.get(url, params=params)
                
                if response.status_code != 200:
                    logger.error(f"Scraper failed with status code: {response.status_code}")
                    return []

                # Google's JSON response starts with a security prefix: )]}'
                # We must strip this before json.loads() can work
                raw_content = response.text.lstrip(")]}'\n")
                data = json.loads(raw_content)

                # The reviews are usually nested in index [2] of the response array
                if len(data) > 2 and data[2]:
                    for r in data[2]:
                        try:
                            # Extracting specific fields from the nested list structure
                            review_item = {
                                "review_id": r[0],
                                "rating": r[4],
                                "text": r[3] if r[3] else "",
                                "author_title": r[1][4][0][4] if (len(r) > 1 and r[1]) else "Anonymous",
                                "timestamp": r[27],
                                "datetime_utc": datetime.fromtimestamp(r[27]/1000, tz=timezone.utc).isoformat()
                            }
                            reviews_list.append(review_item)
                        except (IndexError, TypeError, KeyError):
                            # Skip individual reviews if they are malformed
                            continue

                logger.info(f"Successfully fetched {len(reviews_list)} reviews for {data_id}")
                return reviews_list

            except Exception as e:
                logger.error(f"Scraper encountered a critical error: {str(e)}")
                return []

# --- THIS IS THE FUNCTION YOUR APP IS CURRENTLY MISSING ---
# This acts as the entry point for app.routes.reviews
async def fetch_reviews(data_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Called by the web routes to execute the scraping process.
    """
    scraper = FastGoogleScraper()
    return await scraper.get_reviews(data_id, limit)
