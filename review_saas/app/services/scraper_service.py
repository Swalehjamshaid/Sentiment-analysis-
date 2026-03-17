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
    Specifically designed to work with the 0x hex google_id.
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

    async def get_reviews(self, data_id: str, limit: int = 10000) -> List[Dict[str, Any]]:
        """
        Fetches reviews directly from Google's internal Maps data endpoint.
        
        :param data_id: The unique Google 'google_id' (The 0x hex code).
        :param limit: Number of reviews to fetch. Increased default to 10,000 for full history.
        """
        # Google's raw data endpoint for AJAX-based review retrieval
        url = "https://www.google.com/maps/preview/review/listentitiesreviews"
        
        # Protobuf-style 'pb' parameter:
        # !1m1!1s{data_id} -> Identifies the specific business entity
        # !2i0 -> Start index (offset)
        # !3i{limit} -> Result count (This allows us to fetch 1000+ at once)
        # !4m5!4b1!5b1!6b1!7b1 -> Metadata and formatting flags
        # !5e1 -> Sort order: Newest reviews first
        pb = f"!1m1!1s{data_id}!2i0!3i{limit}!4m5!4b1!5b1!6b1!7b1!5e1"
        
        params = {
            "authuser": "0",
            "hl": "en",
            "gl": "us",
            "pb": pb
        }

        reviews_list = []
        
        # Increase timeout to 60.0 to handle very large data sets (10k reviews)
        async with httpx.AsyncClient(headers=self.headers, timeout=60.0, follow_redirects=True) as client:
            try:
                response = await client.get(url, params=params)
                
                if response.status_code != 200:
                    logger.error(f"Google Scraper Error: Status {response.status_code} for ID: {data_id}")
                    return []

                # Google prefixes their JSON with security characters )]}' to prevent XSSI
                content = response.text
                if content.startswith(")]}'"):
                    content = content[4:].strip()

                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    logger.error("Failed to decode JSON from Google response.")
                    return []

                # Validation of nested list structure
                if not data or not isinstance(data, list):
                    logger.warning(f"Malformed or empty response for data_id: {data_id}")
                    return []

                # Search through the nested list to find the review array
                raw_reviews = []
                for item in data:
                    if isinstance(item, list) and len(item) > 0:
                        # Heuristic: The review list items are lists with > 10 elements
                        if isinstance(item[0], list) and len(item[0]) > 10:
                            raw_reviews = item
                            break
                
                # Fallback to index 0 if the heuristic search fails
                if not raw_reviews and len(data) > 0:
                    raw_reviews = data[0] if data[0] is not None else []

                for r in raw_reviews:
                    try:
                        # Map indices to match your Database Review model
                        # author_title extraction logic
                        author_title = "Google User"
                        if len(r) > 1 and r[1] and len(r[1]) > 4:
                            author_title = r[1][4][0][4]

                        review_item = {
                            "review_id": str(r[0]),
                            "rating": int(r[4]) if len(r) > 4 else 0,
                            "text": r[3] if len(r) > 3 and r[3] else "",
                            "author_title": author_title,
                            "author_id": r[6] if len(r) > 6 else None,
                            # Convert millisecond timestamp (r[27]) to ISO format with UTC awareness
                            # This is critical for the "Date Based" filtering
                            "review_datetime_utc": datetime.fromtimestamp(
                                r[27]/1000, tz=timezone.utc
                            ).isoformat() if (len(r) > 27 and r[27]) else datetime.now(timezone.utc).isoformat(),
                            "owner_answer": r[9][1] if (len(r) > 9 and r[9] and len(r[9]) > 1) else None,
                        }
                        reviews_list.append(review_item)
                    except (IndexError, TypeError, ValueError):
                        # Skip malformed individual review entries
                        continue

            except Exception as e:
                logger.error(f"Unexpected Scraper Error: {str(e)}")
                return []

        logger.info(f"✅ Scraper successfully retrieved {len(reviews_list)} reviews for ID: {data_id}")
        return reviews_list
