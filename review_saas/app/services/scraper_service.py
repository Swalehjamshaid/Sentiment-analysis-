# filename: app/services/scraper.py

import httpx
import json
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class FastGoogleScraper:
    """
    High-speed Google Review scraper utilizing direct AJAX request emulation.
    Optimized for deployment on Railway with standard HTTP libraries.
    """
    def __init__(self):
        # Mobile User-Agent triggers Google's lightweight response format
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_raw_data(self, client: httpx.AsyncClient, url: str, params: dict) -> str:
        """Fetches raw text with retry logic for network stability."""
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.text

    async def get_reviews(self, data_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Extracts reviews directly from Google Maps internal data endpoints.
        
        :param data_id: The unique Google feature_id (Place ID or CID).
        :param limit: Maximum reviews to fetch.
        """
        url = "https://www.google.com/maps/preview/review/listentitiesreviews"
        
        # Protobuf-style string for request parameters
        # !1i0 = start index, !2i{limit} = count, !3e1 = sort by newest
        pb = f"!1m1!1s{data_id}!2m2!1i0!2i{limit}!3e1!4m5!4b1!5b1!6b1!7b1!11m1!4b1"
        
        params = {
            "authuser": "0",
            "hl": "en",
            "gl": "us",
            "pb": pb
        }

        reviews_list = []
        
        async with httpx.AsyncClient(headers=self.headers, timeout=25.0) as client:
            try:
                content = await self.fetch_raw_data(client, url, params)
                
                # Google prefixes their JSON with security characters )]}' to prevent XSSI
                if content.startswith(")]}'"):
                    content = content[4:].strip()

                data = json.loads(content)

                # Validation of Google's nested list response structure
                if not data or not isinstance(data, list) or len(data) < 3:
                    logger.warning(f"Unexpected response format for ID: {data_id}")
                    return []

                # Reviews are contained in index 2
                raw_reviews = data[2] if data[2] else []

                for r in raw_reviews:
                    try:
                        # Defensive extraction to handle potential missing fields in raw data
                        review_item = {
                            "review_id": str(r[0]),
                            "rating": int(r[4]) if len(r) > 4 else 0,
                            "text": r[3] if len(r) > 3 and r[3] else "",
                            "author_name": r[0][1] if (r[0] and len(r[0]) > 1) else "Anonymous",
                            # Google uses millisecond timestamps in index 27
                            "google_review_time": datetime.fromtimestamp(r[27]/1000).isoformat() if (len(r) > 27 and r[27]) else datetime.now().isoformat(),
                        }
                        reviews_list.append(review_item)
                    except (IndexError, TypeError, ValueError) as e:
                        logger.debug(f"Skipping malformed review entry: {e}")
                        continue

            except httpx.HTTPStatusError as e:
                logger.error(f"Google API returned error status: {e.response.status_code}")
            except Exception as e:
                logger.error(f"Scraper Engine Failure: {str(e)}")
                return []

        return reviews_list
