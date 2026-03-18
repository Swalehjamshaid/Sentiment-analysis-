import httpx
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class FastGoogleScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
            "Accept": "*/*",
            "Referer": "https://www.google.com/",
        }

    async def get_reviews(self, data_id: str, limit: int = 10000) -> List[Dict[str, Any]]:
        url = "https://www.google.com/maps/preview/review/listentitiesreviews"
        pb = f"!1m1!1s{data_id}!2i0!3i{limit}!4m5!4b1!5b1!6b1!7b1!5e1"
        params = {"authuser": "0", "hl": "en", "gl": "us", "pb": pb}
        reviews_list = []
        
        async with httpx.AsyncClient(headers=self.headers, timeout=60.0, follow_redirects=True) as client:
            try:
                response = await client.get(url, params=params)
                if response.status_code != 200: return []
                
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
                
                for r in raw_reviews:
                    try:
                        reviews_list.append({
                            "review_id": str(r[0]),
                            "rating": int(r[4]) if len(r) > 4 else 0,
                            "text": r[3] if (len(r) > 3 and r[3]) else "",
                            "author_title": r[1][4][0][4] if (len(r) > 1 and r[1]) else "Google User",
                            "review_datetime_utc": datetime.fromtimestamp(
                                r[27]/1000, tz=timezone.utc
                            ).isoformat() if (len(r) > 27 and r[27]) else datetime.now(timezone.utc).isoformat()
                        })
                    except: continue
            except Exception as e:
                logger.error(f"Scraper Error: {e}")
        return reviews_list
