# filename: app/services/scraper.py

import httpx
import json
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class FastGoogleScraper:
    """
    A high-speed Google Review scraper using direct request emulation.
    Bypasses the overhead of Selenium for 10x faster execution.
    """
    def __init__(self):
        # Mobile User-Agent triggers Google's lightweight AJAX response structure
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
            "Connection": "keep-alive"
        }

    async def get_reviews(self, data_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetches reviews directly from Google's internal Maps data endpoint.
        
        :param data_id: The unique Google 'feature_id' (CID or Place ID).
        :param limit: Number of reviews to fetch per request.
        """
        # Google's raw data endpoint for AJAX-based review retrieval
        url = "https://www.google.com/maps/preview/review/listentitiesreviews"
        
        # Protobuf-style 'pb' parameter:
        # !1m1!1s{data_id} -> Identifies the business
        # !2i0 -> Start index (offset)
        # !3i{limit} -> Result count
        # !4m5!4b1!5b1!6b1!7b1 -> Metadata and formatting flags
        # !5e1 -> Sort by newest first
        pb = f"!1m1!1s{data_id}!2i0!3i{limit}!4m5!4b1!5b1!6b1!7b1!5e1"
        
        params = {
            "authuser": "0",
            "hl": "en",
            "gl": "us",
            "pb": pb
        }

        reviews_list = []
        
        async with httpx.AsyncClient(headers=self.headers, timeout=20.0, follow_redirects=True) as client:
            try:
                response = await client.get(url, params=params)
                
                if response.status_code != 200:
                    logger.error(f"Google Scraper returned status {response.status_code} for ID: {data_id}")
                    return []

                # Google prefixes their JSON with security characters )]}' to prevent XSSI
                content = response.text
                if content.startswith(")]}'"):
                    content = content[4:].strip()

                data = json.loads(content)

                # Validation of nested list structure
                if not data or not isinstance(data, list) or len(data) < 1:
                    logger.warning(f"Malformed or empty response for data_id: {data_id}")
                    return []

                # In this endpoint, reviews are typically in index [0]
                raw_reviews = data[0] if data[0] is not None else []

                for r in raw_reviews:
                    try:
                        # Map indices to match your Database Review model
                        review_item = {
                            "review_id": str(r[0]),
                            "rating": int(r[4]) if len(r) > 4 else 0,
                            "text": r[3] if len(r) > 3 and r[3] else "",
                            "author_name": r[1][4][0][4] if (len(r) > 1 and r[1]) else "Google User",
                            "author_id": r[6] if len(r) > 6 else None,
                            # Google uses millisecond timestamps in index 27
                            "google_review_time": datetime.fromtimestamp(r[27]/1000).isoformat() if (len(r) > 27 and r[27]) else datetime.now().isoformat(),
                            "owner_answer": r[9][1] if (len(r) > 9 and r[9] and len(r[9]) > 1) else None,
                        }
                        reviews_list.append(review_item)
                    except (IndexError, TypeError, ValueError) as e:
                        logger.debug(f"Skipping a review entry due to parsing error: {e}")
                        continue

            except json.JSONDecodeError:
                logger.error("Failed to decode JSON from Google response. Check if the 'pb' format has changed.")
            except Exception as e:
                logger.error(f"Unexpected Scraper Error: {str(e)}")
                return []

        return reviews_list
