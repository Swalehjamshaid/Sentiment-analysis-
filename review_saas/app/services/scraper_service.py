# filename: app/services/scraper.py

import httpx
import json
import logging
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 300, skip: int = 0) -> List[Dict[str, Any]]:
    """
    High-speed Google Review extraction with pagination support.
    :param skip: The starting index (offset) for the fetch.
    """
    url = "https://www.google.com/maps/preview/review/listentitiesreviews"
    
    # Protobuf parameters: 
    # !1i{skip} = Start Index (Offset)
    # !2i{limit} = Number of records to fetch
    # !3e1 = Sort by Newest
    pb = f"!1m1!1s{place_id}!2m2!1i{skip}!2i{limit}!3e1!4m5!4b1!5b1!6b1!7b1!11m1!4b1"
    
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
    
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            content = response.text
            if content.startswith(")]}'"):
                content = content[4:].strip()

            data = json.loads(content)

            if not data or not isinstance(data, list) or len(data) < 3:
                return []

            raw_reviews = data[2] if data[2] else []

            for r in raw_reviews:
                try:
                    review_item = {
                        "review_id": str(r[0]),
                        "rating": int(r[4]) if len(r) > 4 else 0,
                        "text": r[3] if len(r) > 3 and r[3] else "",
                        "author_name": r[0][1] if (r[0] and len(r[0]) > 1) else "Google User",
                        "google_review_time": datetime.fromtimestamp(r[27]/1000).isoformat() if (len(r) > 27 and r[27]) else datetime.utcnow().isoformat()
                    }
                    reviews_list.append(review_item)
                except (IndexError, TypeError, ValueError):
                    continue

        except Exception as e:
            logger.error(f"Scraper Pagination Error for {place_id} at offset {skip}: {str(e)}")
            return []

    return reviews_list
