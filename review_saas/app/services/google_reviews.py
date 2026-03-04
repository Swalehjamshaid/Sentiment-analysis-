from __future__ import annotations
from typing import List
from datetime import datetime, timezone
import googlemaps
import logging
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Company, Review
from app.core.config import settings
from app.services.sentiment import score as get_sentiment_score, label as get_sentiment_label

# Logger setup
logger = logging.getLogger("google_reviews")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)


def fetch_place_details(place_id: str) -> dict:
    try:
        gmaps = googlemaps.Client(key=settings.GOOGLE_PLACES_API_KEY)

        details = gmaps.place(
            place_id=place_id,
            fields=[
                "name",
                "rating",
                "user_ratings_total",
                "reviews",
                "formatted_address",
                "website",
            ],
        )

        logger.info(f"Fetched place details for place_id={place_id}")
        return details.get("result", {})

    except Exception as e:
        logger.error(f"Google API error: {e}")
        return {}


def fetch_google_reviews(place_id: str, max_results: int = 50) -> List[dict]:
    details = fetch_place_details(place_id)
    reviews = details.get("reviews", [])
    logger.info(f"{len(reviews)} reviews received from Google")
    return reviews[:max_results]


async def ingest_company_reviews(company_id: int, place_id: str):
    logger.info(f"Starting ingestion for company_id={company_id}")

    reviews_data = fetch_google_reviews(place_id)

    if not reviews_data:
        logger.warning("No reviews returned from Google.")
        return

    async with get_session() as session:
        try:
            result = await session.execute(
                select(Company).where(Company.id == company_id)
            )
            company: Company = result.scalar_one_or_none()

            if not company:
                logger.error(f"Company {company_id} not found.")
                return

            added_count = 0

            for r in reviews_data:
                source_id = f"{place_id}_{r.get('author_name','unknown')}_{r.get('time',0)}"

                # Prevent duplicates
                existing = await session.execute(
                    select(Review).where(Review.source_id == source_id)
                )
                if existing.scalar_one_or_none():
                    continue

                text_content = r.get("text", "")

                sentiment_score = get_sentiment_score(text_content)
                sentiment_label = get_sentiment_label(sentiment_score)

                review_time = datetime.fromtimestamp(
                    r.get("time", 0), tz=timezone.utc
                )

                new_review = Review(
                    company_id=company.id,
                    source_id=source_id,
                    author_name=r.get("author_name"),
                    rating=int(r.get("rating", 0)),
                    text=text_content,
                    google_review_time=review_time,
                    sentiment_score=sentiment_score,
                    sentiment_label=sentiment_label,
                )

                session.add(new_review)
                added_count += 1

            # IMPORTANT: Commit to save reviews
            await session.commit()

            logger.info(f"Successfully saved {added_count} new reviews.")

        except Exception as e:
            await session.rollback()
            logger.error(f"Database error during ingestion: {e}")
