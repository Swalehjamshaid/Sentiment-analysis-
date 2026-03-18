# filename: app/services/scraper.py

import httpx
import json
import logging
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class FastGoogleScraper:
    """
    High-speed Google Review scraper using direct request emulation.
    """

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        }

    async def get_reviews(self, data_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        url = "https://www.google.com/maps/preview/review/listentitiesreviews"

        pb = f"!1m1!1s{data_id}!2m2!1i0!2i{limit}!3e1!4m5!4b1!5b1!6b1!7b1!11m1!4b1"

        params = {
            "authuser": "0",
            "hl": "en",
            "gl": "us",
            "pb": pb
        }

        reviews_list = []

        async with httpx.AsyncClient(headers=self.headers, timeout=20.0) as client:
            try:
                response = await client.get(url, params=params)
                content = response.text

                if content.startswith(")]}'"):
                    content = content[4:].strip()

                data = json.loads(content)

                if not data or not isinstance(data, list) or len(data) < 3:
                    logger.warning(f"No valid data returned for ID: {data_id}")
                    return []

                raw_reviews = data[2] if data[2] else []

                for r in raw_reviews:
                    try:
                        review_item = {
                            "review_id": str(r[0]),
                            "rating": int(r[4]) if len(r) > 4 else 0,
                            "text": r[3] if len(r) > 3 and r[3] else "",
                            "author_name": "Google User",
                            "google_review_time": datetime.fromtimestamp(r[27]/1000).isoformat()
                            if (len(r) > 27 and r[27]) else datetime.now().isoformat(),
                        }
                        reviews_list.append(review_item)
                    except Exception:
                        continue

            except Exception as e:
                logger.error(f"Fast Scraper Engine Failure: {str(e)}")
                return []

        return reviews_list


# ✅ IMPORTANT: GLOBAL FUNCTION (THIS FIXES YOUR SYSTEM)
scraper = FastGoogleScraper()


async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Standard function used by reviews router.
    This fixes import + router loading issue.
    """
    return await scraper.get_reviews(place_id, limit)
