# filename: app/services/scraper.py
import httpx
import json
import logging
import re
from datetime import datetime
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=10))
async def fetch_reviews(place_id: str, limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
    # 2026 Stable Search Endpoint
    url = f"https://www.google.com/maps/preview/review/listentitiesreviews"
    
    # This 'pb' is specifically formatted for Google Search Review results
    # It bypasses the 404 error by using the direct Search API structure
    pb = f"!1m1!1s{place_id}!2m2!1i{skip}!2i{limit}!3e1!4m5!4b1!5b1!6b1!7b1!11m1!4b1"
    
    params = {
        "authuser": "0",
        "hl": "en",
        "gl": "us",
        "pb": pb
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "https://www.google.com/",
        "x-goog-maps-rit-id": "1"
    }

    reviews_list = []
    
    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        try:
            response = await client.get(url, params=params)
            
            # If we get a 404 or 403, Google is blocking the specific URL structure
            if response.status_code != 200:
                logger.error(f"Google Refusal {response.status_code} at {url}")
                return []

            content = response.text
            if content.startswith(")]}'"):
                content = content[4:].strip()

            data = json.loads(content)
            
            # Data structure navigation for Google Reviews JSON
            if not data or len(data) < 3:
                return []

            raw_reviews = data[2] or []
            for r in raw_reviews:
                try:
                    # Mapping the complex Google List to our dictionary
                    reviews_list.append({
                        "review_id": str(r[0]),
                        "rating": int(r[4]) if len(r) > 4 else 0,
                        "text": r[3] if (len(r) > 3 and r[3]) else "No comment",
                        "author_name": r[0][1] if (r[0] and len(r[0]) > 1) else "Google User",
                        "google_review_time": datetime.fromtimestamp(r[27]/1000).isoformat() if (len(r) > 27 and r[27]) else datetime.utcnow().isoformat()
                    })
                except (IndexError, TypeError, KeyError):
                    continue
            
            logger.info(f"Successfully scraped {len(reviews_list)} reviews for {place_id}")
            return reviews_list

        except Exception as e:
            logger.error(f"Scraper Error: {str(e)}")
            raise
