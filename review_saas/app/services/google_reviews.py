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
    MAX_REVIEWS_PER_CALL = 50  # Can adjust as needed

    def __init__(self, api_client):
        self.client = api_client

    def fetch_reviews(
        self, 
        place_id: str, 
        max_reviews: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[ReviewData]:
        """Fetch reviews with pagination and optional date filter, storing all fields"""
        all_reviews = []
        offset = 0

        while True:
            remaining = max_reviews - len(all_reviews) if max_reviews else self.MAX_REVIEWS_PER_CALL
            limit = min(self.MAX_REVIEWS_PER_CALL, remaining)

            response = self.client.get_reviews(place_id=place_id, limit=limit, offset=offset)
            if not response.get("reviews"):
                break

            for r in response["reviews"]:
                review_time = datetime.fromtimestamp(r.get("time", datetime.now().timestamp()))
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
                    competitor_name=r.get("competitor_name"),  # If present
                    additional_fields=r  # Store all other fields for flexibility
                )
                all_reviews.append(review)

            offset += limit
            if max_reviews and len(all_reviews) >= max_reviews:
                break
            if len(response["reviews"]) < limit:
                break  # No more reviews available

        return all_reviews

def ingest_company_reviews(
    company_id: str, 
    api_client, 
    start_date: Optional[datetime] = None, 
    end_date: Optional[datetime] = None,
    max_reviews: Optional[int] = 10000
) -> CompanyReviews:
    """Fetch and store all reviews for a company within optional date range and max reviews"""
    service = OutscraperReviewsService(api_client)
    reviews_data = service.fetch_reviews(
        place_id=company_id, 
        max_reviews=max_reviews,
        start_date=start_date,
        end_date=end_date
    )
    company_reviews = CompanyReviews(company_id=company_id)
    for review in reviews_data:
        company_reviews.add_review(review)

    logger.info(f"Fetched {len(company_reviews.reviews)} reviews for company {company_id}")
    logger.info(f"Rating Summary: {company_reviews.rating_summary()}")
    logger.info(f"Rating Distribution: {company_reviews.rating_distribution()}")
    logger.info(f"AI Summary: {company_reviews.generate_summary()}")

    return company_reviews
