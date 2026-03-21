import httpx
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

# Standard logging
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
# IMPORTANT: Replace with your actual ZenRows API Key
ZENROWS_API_KEY = "YOUR_ZENROWS_API_KEY"  
ZENROWS_API_URL = "https://api.zenrows.com/v1/"

class ZenRowsGoogleScraper:
    def __init__(self):
        self.api_key = ZENROWS_API_KEY

    async def get_reviews(self, place_id: str, max_reviews: int = 1000) -> List[Dict[str, Any]]:
        all_reviews = []
        offset = 0
        page_size = 100 

        async with httpx.AsyncClient(timeout=60.0) as client:
            while len(all_reviews) < max_reviews:
                # Target URL using the internal Google endpoint (Grey Hat method)
                target_url = f"https://www.google.com/maps/preview/review/listentitiesreviews?authuser=0&hl=en&gl=us&pb=!1m1!1s{place_id}!2i{offset}!3i{page_size}!4m5!4b1!5b1!6b1!7b1!5e1"
                
                # ZenRows Managed Parameters
                params = {
                    "apikey": self.api_key,
                    "url": target_url,
                    "premium_proxy": "true",
                    "proxy_country": "us",
                    "js_render": "true"
                }

                try:
                    response = await client.get(ZENROWS_API_URL, params=params)
                    
                    if response.status_code != 200:
                        logger.error(f"ZenRows Error: {response.status_code}")
                        break

                    # Strip Google's security prefix: )]}'
                    raw_text = response.text.lstrip(")]}'\n")
                    data = json.loads(raw_text)

                    # Ensure the response has data at the expected index
                    if len(data) <= 2 or not data[2]:
                        break 
                    
                    batch = data[2]
                    for r in batch:
                        if len(all_reviews) >= max_reviews:
                            break
                        try:
                            # Casting data to explicit Python types ensures SQLAlchemy alignment
                            all_reviews.append({
                                "review_id": str(r[0]),
                                "rating": int(r[4]),
                                "text": str(r[3]) if r[3] else "",
                                "author": str(r[1][4][0][4]) if (len(r) > 1 and r[1]) else "Anonymous",
                                "timestamp_ms": r[27],
                                "date": datetime.fromtimestamp(r[27]/1000, tz=timezone.utc).isoformat()
                            })
                        except (IndexError, TypeError, KeyError):
                            continue

                    # Break if no more reviews are returned from Google
                    if len(batch) < page_size:
                        break

                    offset += page_size
                    # Short delay to keep requests looking natural
                    await asyncio.sleep(0.2)

                except Exception as e:
                    logger.error(f"Scraper Error: {str(e)}")
                    break

        return all_reviews

# --- PROJECT ALIGNMENT BRIDGE ---
# This matches your routes/reviews.py call: fetch_reviews(place_id=target_id, limit=300)
async def fetch_reviews(place_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Entry point that aligns perfectly with your existing route logic.
    Requires ZERO changes to other project files.
    """
    scraper = ZenRowsGoogleScraper()
    return await scraper.get_reviews(place_id=place_id, max_reviews=limit)
