import httpx
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

# Set up logging so you can see the scraping progress in Railway logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FastGoogleScraper:
    def __init__(self):
        # Mobile headers to mimic a real iPhone user and bypass bot detection
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
            "Accept": "*/*",
            "Referer": "https://www.google.com/",
            "Host": "www.google.com",
        }
        self.base_url = "https://www.google.com/maps/preview/review/listentitiesreviews"

    async def get_reviews(self, data_id: str, max_reviews: int = 1000) -> List[Dict[str, Any]]:
        """
        Fetches up to max_reviews by looping through Google's internal pagination.
        """
        all_reviews = []
        offset = 0
        page_size = 100  # Fetching in chunks of 100 is the most stable speed

        async with httpx.AsyncClient(headers=self.headers, timeout=30.0, follow_redirects=True) as client:
            while len(all_reviews) < max_reviews:
                # The 'pb' parameter handles the Data ID and the Pagination offset (!2i{offset})
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

                    # Strip Google's security prefix: )]}'
                    raw_text = response.text.lstrip(")]}'\n")
                    data = json.loads(raw_text)

                    # Path to the reviews array in Google's internal JSON structure
                    if len(data) <= 2 or not data[2]:
                        break  # No more reviews found
                    
                    batch = data[2]
                    for r in batch:
                        if len(all_reviews) >= max_reviews:
                            break
                        
                        try:
                            # Mapping Google's nested list to a clean dictionary for your AI
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

                    # If the batch is smaller than requested, we've reached the end
                    if len(batch) < page_size:
                        break

                    offset += page_size
                    
                    # 0.5s delay to remain 'Grey Hat' and avoid IP blocks
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.error(f"Scraper Loop Error: {str(e)}")
                    break

        logger.info(f"Successfully collected {len(all_reviews)} reviews for {data_id}")
        return all_reviews

# --- ALIGNMENT WRAPPER (CRITICAL FIX) ---
# This matches the 'from app.services.scraper import fetch_reviews' in your routes
async def fetch_reviews(data_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    This is the primary entry point for your FastAPI/Flask routes.
    It ensures the rest of your project code 'aligns' with this new file.
    """
    scraper = FastGoogleScraper()
    return await scraper.get_reviews(data_id, max_reviews=limit)
