# filename: app/services/scraper.py

from __future__ import annotations
import logging
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class Scraper:
    """Internal scraper (No external API) with date filtering"""

    def __init__(self):
        logger.info("✅ Internal Scraper initialized (No external API)")

    async def fetch_reviews(
        self,
        query: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:

        start = datetime.fromisoformat(start_date) if start_date else None
        end = datetime.fromisoformat(end_date) if end_date else None

        reviews: List[Dict[str, Any]] = []

        sample_reviews = [
            ("Excellent service and friendly staff!", 5),
            ("Good experience overall", 4),
            ("Average service, can improve", 3),
            ("Not satisfied with the quality", 2),
            ("Very bad experience", 1),
            ("Loved the ambiance and service!", 5),
            ("Delivery was late but product was good", 3),
            ("Customer support was very helpful", 4),
            ("Terrible management", 1),
            ("Highly recommended!", 5),
        ]

        now = datetime.utcnow()

        i = 0
        while True:  # unlimited generation
            text, rating = random.choice(sample_reviews)
            review_date = now - timedelta(days=random.randint(0, 1500))

            if start and review_date < start:
                continue
            if end and review_date > end:
                continue

            reviews.append({
                "review_id": f"rev_{i}_{int(review_date.timestamp())}",
                "author": f"User_{random.randint(1000,9999)}",
                "rating": rating,
                "text": text,
                "date": review_date.isoformat(),
                "response": None,
                "response_date": None,
            })
            i += 1

            if i >= 10000:  # safety stop for demo
                break

        logger.info(f"✅ Generated {len(reviews)} reviews")
        return reviews
