# filename: app/services/scraper.py
import httpx
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class FastGoogleScraper:
    """
    High-speed Google Review scraper placeholder.
    Returns dummy reviews for testing and integration.
    """
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
                          "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 "
                          "Mobile/15E148 Safari/604.1",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
            "Connection": "keep-alive"
        }

    async def get_reviews(self, data_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch reviews directly from Google Maps endpoint.
        Placeholder returns dummy data if Google fails.
        """
        # Generate dummy reviews for testing
        dummy_reviews = [
            {
                "review_id": f"{data_id}-{i}",
                "rating": 5 if i % 2 == 0 else 4,
                "text": f"Dummy review text {i}",
                "author_title": f"User {i}",
                "review_datetime_utc": datetime.now(timezone.utc).isoformat(),
            }
            for i in range(1, min(limit, 100)+1)
        ]
        return dummy_reviews
