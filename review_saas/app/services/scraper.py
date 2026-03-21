import httpx
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

# Standard logging for Railway deployment monitoring
logger = logging.getLogger(__name__)

class FastGoogleScraper:
    def __init__(self):
        # Mobile headers to mimic a real iPhone user for higher success rates
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
            "Accept": "*/*",
            "Referer": "https://www.google.com/",
            "Host": "www.google.com",
        }
        self.base_url = "https://www.google.com/maps/preview/review/listentitiesreviews"

    async def get_reviews(self, data_id: str, max_reviews: int = 1000) -> List[Dict[str, Any]]:
        """
        Loops through Google's internal data in chunks of 100 to reach the 1,000+ goal.
        """
        all_reviews = []
        offset = 0
        page_size = 100 

        async with httpx.AsyncClient(headers=self.headers, timeout=30.0, follow_redirects=True) as client:
            while len(all_reviews) < max_reviews:
                # pb parameter: !2i{offset} is the starting point, !3i{page_size} is the count
                pb = f"!1m1!1s{data_id}!2i{offset}!3i{page_size}!4m5!4b1!5b1!6b1!7b1!5e1"
                params = {
                    "authuser": "0",
                    "hl": "en",
                    "gl": "us",
                    "pb": pb
                }

                try:
                    response = await client.get(self.base_url, params=params)
                    
                    if response.status_code != 200:
                        logger.error(f"Scraper hit an error: {response.status_code} at offset {offset}")
                        break

                    # Strip the security prefix Google uses to block scrapers
                    raw_text = response.text.lstrip(")]}'\n")
                    data = json.loads(raw_text)

                    # Check if reviews exist in the expected JSON index
                    if len(data) <= 2 or not data[2]:
                        break 
                    
                    batch = data[2]
                    for r in batch:
                        if len(all_reviews) >= max_reviews:
                            break
                        
                        try:
                            # Standard dictionary format for Sentiment Analysis compatibility
                            all_reviews.append({
                                "review_id": r[0],
                                "rating": r[4],
                                "text": r[3] if r[3] else "",
                                "author": r[1][4][0][4] if (len(r) > 1 and r[1]) else "Anonymous",
                                "timestamp_ms": r[27],
                                "date": datetime.fromtimestamp(r[27]/1000, tz=timezone.utc).isoformat()
                            })
                        except (IndexError, TypeError):
                            continue

                    # If we got less than the page_size, there are no more reviews to fetch
                    if len(batch) < page_size:
                        break

                    offset += page_size
                    
                    # Small delay to keep the request 'Grey Hat' and human-like
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.error(f"Critical error in scraper loop: {str(e)}")
                    break

        logger.info(f"Scraper finished. Total reviews for {data_id}: {len(all_reviews)}")
        return all_reviews

# --- PROJECT ALIGNMENT BRIDGE ---
# This name MUST match your 'from app.services.scraper import fetch_reviews' in main.py
async def fetch_reviews(data_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    The only entry point required by the rest of your project. 
    Requires no changes to routes/reviews.py or main.py.
    """
    scraper = FastGoogleScraper()
    return await scraper.get_reviews(data_id, max_reviews=limit)
