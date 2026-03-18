# filename: app/services/scraper.py
import httpx
import json
import logging
from datetime import datetime
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_reviews(place_id: str, limit: int = 300, skip: int = 0) -> List[Dict[str, Any]]:
    # Corrected Google Maps internal reviews endpoint
    url = "https://www.google.com/maps/preview/review/listentitiesreviews"
    
    # pb parameter: This is the exact encoding Google expects
    pb = f"!1m1!1s{place_id}!2m2!1i{skip}!2i{limit}!3e1!4m5!4b1!5b1!6b1!7b1!11m1!4b1"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": f"https://www.google.com/maps/place/?q=place_id:{place_id}",
    }
    
    params = {
        "authuser": "0",
        "hl": "en",
        "gl": "us",
        "pb": pb
    }
    
    reviews_list = []
    
    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        try:
            response = await client.get(url, params=params)
            
            # If Google returns 400, it usually means the URL or PB parameter is malformed
            if response.status_code != 200:
                logger.error(f"Google API Error: {response.status_code} for {place_id}")
                return []

            content = response.text
            if content.startswith(")]}'"):
                content = content[4:].strip()

            data = json.loads(content)
            
            if not data or not isinstance(data, list) or len(data) < 3:
                return []

            raw_reviews = data[2] if data[2] else []
            for r in raw_reviews:
                try:
                    reviews_list.append({
                        "review_id": str(r[0]),
                        "rating": int(r[4]) if len(r) > 4 else 0,
                        "text": r[3] if len(r) > 3 and r[3] else "",
                        "author_name": r[0][1] if (r[0] and len(r[0]) > 1) else "Google User",
                        "google_review_time": datetime.fromtimestamp(r[27]/1000).isoformat() if (len(r) > 27 and r[27]) else datetime.utcnow().isoformat()
                    })
                except Exception:
                    continue
                    
            return reviews_list

        except Exception as e:
            logger.error(f"Scraper error for {place_id}: {e}")
            raise
