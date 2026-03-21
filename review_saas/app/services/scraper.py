import httpx
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

# Standard logging so you can see progress in Railway
logger = logging.getLogger(__name__)

class FastGoogleScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15.0; Like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Accept": "*/*",
            "Host": "www.google.com",
        }
        self.base_url = "https://www.google.com/maps/preview/review/listentitiesreviews"

    async def get_reviews(self, data_id: str, max_reviews: int = 1000) -> List[Dict[str, Any]]:
        all_reviews = []
        offset = 0
        page_size = 100 

        async with httpx.AsyncClient(headers=self.headers, timeout=30.0, follow_redirects=True) as client:
            while len(all_reviews) < max_reviews:
                # The 'pb' parameter handles the Data ID and the Pagination offset
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
                        logger.error(f"Google Error: {response.status_code} at offset {offset}")
                        break

                    # Cleaning the security prefix )]}' from Google's response
                    raw_text = response.text.lstrip(")]}'\n")
                    data = json.loads(raw_text)

                    # reviews are located in the 3rd index [2]
                    if len(data) <= 2 or not data[2]:
                        break 
                    
                    batch = data[2]
                    for r in batch:
                        if len(all_reviews) >= max_reviews:
                            break
                        
                        try:
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

                    # If the batch is smaller than requested, we've reached the end of the reviews
                    if len(batch) < page_size:
                        break

                    offset += page_size
                    # 0.5s delay to avoid IP blocking
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.error(f"Scraper Loop Error: {str(e)}")
                    break

        return all_reviews

# --- ALIGNMENT WRAPPER ---
# This matches the 'from app.services.scraper import fetch_reviews' in your routes
async def fetch_reviews(data_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    This function bridges your existing project routes to the new fast scraper.
    """
    scraper = FastGoogleScraper()
    return await scraper.get_reviews(data_id, max_reviews=limit)
