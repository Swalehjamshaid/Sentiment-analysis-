# File: review_saas/app/services/google_reviews.py
from __future__ import annotations
import logging
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from collections import Counter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class ReviewData:
    review_id: str
    author_name: str
    rating: float
    text: str
    time_created: datetime
    sentiment: Optional[str] = None  # positive/neutral/negative
    review_title: Optional[str] = None
    helpful_votes: Optional[int] = 0
    source_platform: Optional[str] = None  # e.g., Google, Yelp
    competitor_name: Optional[str] = None
    additional_fields: Dict[str, any] = field(default_factory=dict)  # Store any extra dynamic fields


@dataclass
class CompanyReviews:
    company_id: str
    reviews: List[ReviewData] = field(default_factory=list)

    def add_review(self, review: ReviewData):
        self.reviews.append(review)

    def rating_summary(self) -> Dict[str, float]:
        """Return average, min, max, and count of ratings"""
        if not self.reviews:
            return {"average": 0, "min": 0, "max": 0, "count": 0}
        ratings = [r.rating for r in self.reviews]
        return {
            "average": sum(ratings) / len(ratings),
            "min": min(ratings),
            "max": max(ratings),
            "count": len(ratings)
        }

    def rating_distribution(self) -> Dict[int, int]:
        """Return count of each rating 1-5"""
        dist = Counter(r.rating for r in self.reviews)
        return {i: dist.get(i, 0) for i in range(1, 6)}

    def generate_summary(self) -> str:
        """Generate AI-powered summary of reviews"""
        summary = (
            f"Total Reviews: {len(self.reviews)}, "
            f"Avg Rating: {self.rating_summary()['average']:.2f}, "
            f"Max Rating: {self.rating_summary()['max']}, "
            f"Min Rating: {self.rating_summary()['min']}"
        )
        return summary


class OutscraperReviewsService:
    """Fetch reviews from Outscraper or Google API"""
    PAGE_SIZE = 100  # Increased for faster full fetch (adjust based on API limits)

    def __init__(self, api_client):
        self.client = api_client

    def fetch_reviews(
        self,
        place_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_reviews: Optional[int] = None  # Optional hard cap (default None = unlimited)
    ) -> List[ReviewData]:
        """
        Fetch ALL reviews within the given date range.
        No artificial limit unless max_reviews is explicitly set.
        """
        all_reviews = []
        offset = 0
        page = 1

        while True:
            logger.info(f"Fetching page {page} for place_id {place_id} (offset={offset})")

            response = self.client.get_reviews(
                place_id=place_id,
                limit=self.PAGE_SIZE,
                offset=offset
            )

            page_reviews = response.get("reviews", [])
            if not page_reviews:
                logger.info("No more reviews returned. Fetch complete.")
                break

            for r in page_reviews:
                try:
                    review_time = datetime.fromtimestamp(r.get("time", datetime.now().timestamp()))
                except (TypeError, ValueError):
                    review_time = datetime.now()  # fallback

                # Strict date filtering from frontend
                if start_date and review_time < start_date:
                    continue
                if end_date and review_time > end_date:
                    continue

                review = ReviewData(
                    review_id=r.get("review_id"),
                    author_name=r.get("author_name"),
                    rating=float(r.get("rating", 0)),
                    text=r.get("text", ""),
                    time_created=review_time,
                    review_title=r.get("title"),
                    helpful_votes=r.get("helpful_votes", 0),
                    source_platform=r.get("platform", "Google"),
                    competitor_name=r.get("competitor_name"),
                    additional_fields=r  # Keep everything else
                )
                all_reviews.append(review)

            logger.info(f"Page {page}: added {len(page_reviews)} reviews (total so far: {len(all_reviews)})")

            offset += self.PAGE_SIZE
            page += 1

            # Optional hard cap (only if explicitly requested)
            if max_reviews and len(all_reviews) >= max_reviews:
                logger.info(f"Reached requested max_reviews limit ({max_reviews})")
                break

        return all_reviews


def ingest_company_reviews(
    place_id: str,
    company_id: str,
    api_client,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    max_reviews: Optional[int] = None  # Default None = fetch everything
) -> CompanyReviews:
    """
    Fetch and store reviews for a company, respecting frontend date range.
    No limit unless max_reviews is explicitly passed.
    """
    service = OutscraperReviewsService(api_client)

    logger.info(
        f"Starting full review fetch for company {company_id} "
        f"(place_id: {place_id}), range: {start_date or 'any'} → {end_date or 'any'}"
    )

    reviews_data = service.fetch_reviews(
        place_id=place_id,
        start_date=start_date,
        end_date=end_date,
        max_reviews=max_reviews
    )

    company_reviews = CompanyReviews(company_id=company_id)

    for review in reviews_data:
        company_reviews.add_review(review)

    count = len(company_reviews.reviews)
    logger.info(f"Completed: Fetched {count} reviews for company {company_id} (place_id: {place_id})")

    if count > 0:
        logger.info(f"Rating Summary: {company_reviews.rating_summary()}")
        logger.info(f"Rating Distribution: {company_reviews.rating_distribution()}")
        logger.info(f"AI Summary: {company_reviews.generate_summary()}")
    else:
        logger.warning("No reviews found in the selected date range.")

    return company_reviews
