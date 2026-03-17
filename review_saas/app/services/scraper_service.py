import httpx
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class FastGoogleScraper:
    """
    A high-speed Google Review scraper using direct request emulation.
    Bypasses the overhead of Selenium for 10x faster execution.
    """
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
            "Connection": "keep-alive"
        }

    async def get_reviews(self, data_id: str, limit: int = 10000) -> List[Dict[str, Any]]:
        """
        Fetches reviews directly from Google's internal Maps data endpoint.
        :param data_id: The unique Google 'google_id' (The 0x hex code).
        :param limit: Number of reviews to fetch. Default 10,000.
        """
        url = "https://www.google.com/maps/preview/review/listentitiesreviews"
        
        # pb parameter: !3i{limit} handles the high-capacity result count
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
                    logger.error(f"Google Scraper Error: Status {response.status_code}")
                    return []

                content = response.text
                if content.startswith(")]}'"):
                    content = content[4:].strip()

                data = json.loads(content)
                raw_reviews = []
                
                for item in data:
                    if isinstance(item, list) and len(item) > 0:
                        if isinstance(item[0], list) and len(item[0]) > 10:
                            raw_reviews = item
                            break
                
                if not raw_reviews and len(data) > 0:
                    raw_reviews = data[0] if data[0] is not None else []

                for r in raw_reviews:
                    try:
                        author_title = "Google User"
                        if len(r) > 1 and r[1] and len(r[1]) > 4:
                            author_title = r[1][4][0][4]

                        reviews_list.append({
                            "review_id": str(r[0]),
                            "rating": int(r[4]) if len(r) > 4 else 0,
                            "text": r[3] if len(r) > 3 and r[3] else "",
                            "author_title": author_title,
                            "review_datetime_utc": datetime.fromtimestamp(
                                r[27]/1000, tz=timezone.utc
                            ).isoformat() if (len(r) > 27 and r[27]) else datetime.now(timezone.utc).isoformat(),
                        })
                    except: continue

            except Exception as e:
                logger.error(f"Scraper Error: {str(e)}")
                return []

        return reviews_list
