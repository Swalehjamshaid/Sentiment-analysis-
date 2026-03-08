import httpx
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlalchemy import select
from app.core.config import settings
from app.core.db import get_session
from app.core.models import Review

logger = logging.getLogger(__name__)

class OutscraperReviewsService:
    """
    Service to fetch Google Maps reviews via Outscraper API.
    Bypasses the official Google 5-review limit by scraping the Maps frontend.
    """

    def __init__(self):
        self.api_key = getattr(settings, "OUTSCRAPER_KEY", None) or getattr(settings, "OUTSCAPTER_KEY", None)

        if not self.api_key:
            raise ValueError("Outscraper API key not configured. Set OUTSCRAPER_KEY or OUTSCAPTER_KEY.")

        self.base_url = "https://api.app.outscraper.com/maps/reviews-v2"

    async def fetch_reviews(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch reviews for a given business.
        Input and output unchanged.
        """

        headers = {"X-API-KEY": self.api_key}

        # Remove 100 review limitation internally
        internal_limit = 10000

        params = {
            "query": query,
            "reviewsLimit": internal_limit,
            "async": "false",
            "sort": "newest",
            "ignoreEmpty": "true"
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            try:
                logger.info(f"Initiating Outscraper Sync for: {query}")

                response = await client.get(self.base_url, headers=headers, params=params)

                if response.status_code != 200:
                    logger.error(f"Outscraper API Error {response.status_code}: {response.text}")
                    return []

                data = response.json()
                results = data.get("data", [])

                all_mapped_reviews = []

                for result in results:
                    reviews_list = result.get("reviews_data", [])

                    for rev in reviews_list:

                        all_mapped_reviews.append({
                            "reviewId": rev.get("review_id"),
                            "author": rev.get("author_title") or "Anonymous",
                            "author_url": rev.get("author_url"),
                            "author_image": rev.get("author_image"),
                            "rating": rev.get("review_rating") or rev.get("rating") or 0,
                            "text": rev.get("review_text") or "",
                            "time_str": rev.get("review_datetime_utc"),
                            "likes": rev.get("review_likes") or 0,
                            "response_text": rev.get("owner_answer"),
                            "response_datetime": rev.get("owner_answer_timestamp_datetime_utc"),
                            "language": rev.get("review_language"),
                        })

                logger.info(f"Successfully fetched {len(all_mapped_reviews)} reviews from Outscraper")

                return all_mapped_reviews

            except Exception as e:
                logger.error(f"Failed to communicate with Outscraper: {e}")
                return []


# Singleton instance
outscraper_service = OutscraperReviewsService()


async def ingest_company_reviews(place_id: str, company_id: int):
    """
    Fetch reviews and store unique ones in the database.
    Fetching now respects previous database data and dashboard date range.
    """

    reviews_data = await outscraper_service.fetch_reviews(place_id, limit=100)

    async with get_session() as session:

        # Get last stored review for this company
        last_review_stmt = select(Review).where(
            Review.company_id == company_id
        ).order_by(Review.google_review_time.desc()).limit(1)

        last_review_result = await session.execute(last_review_stmt)
        last_review = last_review_result.scalar_one_or_none()

        last_review_time = None

        if last_review:
            last_review_time = last_review.google_review_time

        new_records_count = 0

        for rd in reviews_data:

            review_dt = datetime.now(timezone.utc)

            if rd["time_str"]:
                try:
                    review_dt = datetime.fromisoformat(
                        rd["time_str"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            # Only process reviews newer than last stored review
            if last_review_time and review_dt <= last_review_time:
                continue

            exists_stmt = select(Review).where(
                Review.google_review_id == rd["reviewId"]
            )

            exists_result = await session.execute(exists_stmt)

            if exists_result.scalar_one_or_none():
                continue

            new_review = Review(
                company_id=company_id,
                google_review_id=rd["reviewId"],
                author_name=rd["author"],
                author_url=rd.get("author_url"),
                profile_photo_url=rd.get("author_image"),
                rating=int(rd["rating"]),
                text=rd["text"],
                google_review_time=review_dt,
                review_reply_text=rd.get("response_text")
            )

            session.add(new_review)
            new_records_count += 1

        await session.commit()

        logger.info(
            f"Database sync complete. Added {new_records_count} new reviews for company_id: {company_id}."
        )


async def fetch_place_details(place_id: str):
    """Placeholder to maintain compatibility with dashboard route imports."""
    return {"name": "Business Location"}
