# filename: app/services/scraper.py

import httpx
import json
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_reviews(place_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    High-speed Google Review extraction. 
    Synchronized with reviews.py router expectations.
    """
    # Google AJAX endpoint
    url = "https://www.google.com/maps/preview/review/listentitiesreviews"
    
    # Protobuf parameters: !1s{id}=Business, !1i0=Start, !2i{limit}=Count, !3e1=Newest
    pb = f"!1m1!1s{place_id}!2m2!1i0!2i{limit}!3e1!4m5!4b1!5b1!6b1!7b1!11m1!4b1"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
        "Referer": "https://www.google.com/"
    }
    
    params = {
        "authuser": "0",
        "hl": "en",
        "gl": "us",
        "pb": pb
    }

    reviews_list = []
    
    async with httpx.AsyncClient(headers=headers, timeout=25.0) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            content = response.text
            # Strip Google's anti-XSSI security prefix
            if content.startswith(")]}'"):
                content = content[4:].strip()

            data = json.loads(content)

            # Standard Google Maps AJAX list structure (reviews at index 2)
            if not data or not isinstance(data, list) or len(data) < 3:
                logger.warning(f"Empty or malformed response for Place ID: {place_id}")
                return []

            raw_reviews = data[2] if data[2] else []

            for r in raw_reviews:
                try:
                    # Map to the dictionary structure expected by reviews.py
                    review_item = {
                        "review_id": str(r[0]),
                        "rating": int(r[4]) if len(r) > 4 else 0,
                        "text": r[3] if len(r) > 3 and r[3] else "",
                        "author_name": r[0][1] if (r[0] and len(r[0]) > 1) else "Google User",
                        # Google uses millisecond timestamps at index 27
                        "google_review_time": datetime.fromtimestamp(r[27]/1000).isoformat() if (len(r) > 27 and r[27]) else datetime.utcnow().isoformat()
                    }
                    reviews_list.append(review_item)
                except (IndexError, TypeError, ValueError):
                    continue

        except Exception as e:
            logger.error(f"Scraper Engine Error for {place_id}: {str(e)}")
            return []

    return reviews_list
