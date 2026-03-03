# filename: app/services/google_reviews.py
import googlemaps
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.models import Company, Review
from app.core.config import settings
from app.services.sentiment import score as get_sentiment_score, label as get_sentiment_label

class GoogleReviewsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        api_key = settings.GOOGLE_PLACES_API_KEY
        self.gmaps = googlemaps.Client(key=api_key)

    async def ingest_company_reviews(self, company_id: int, place_id: str):
        details = self.gmaps.place(place_id=place_id, fields=["rating", "reviews", "user_ratings_total"])
        result = details.get("result", {})
        reviews_data = result.get("reviews", [])

        for r in reviews_data:
            source_id = str(r.get('time'))
            stmt = select(Review.id).where(Review.company_id == company_id, Review.source_id == source_id)
            existing = (await self.db.execute(stmt)).scalar_one_or_none()
            
            if not existing:
                text = r.get("text", "")
                s_score = get_sentiment_score(text)
                new_review = Review(
                    company_id=company_id,
                    source_id=source_id,
                    author_name=r.get("author_name"),
                    rating=r.get("rating"),
                    text=text,
                    review_time=datetime.fromtimestamp(r.get("time"), tz=timezone.utc),
                    sentiment_score=s_score,
                    sentiment_label=get_sentiment_label(s_score)
                )
                self.db.add(new_review)

        await self.db.execute(
            update(Company).where(Company.id == company_id).values(
                avg_rating=result.get("rating", 0.0),
                review_count=result.get("user_ratings_total", 0),
                last_updated=datetime.now(tz=timezone.utc)
            )
        )
        await self.db.commit()

async def run_ingestion(session: AsyncSession, company_id: int, place_id: str):
    service = GoogleReviewsService(session)
    await service.ingest_company_reviews(company_id, place_id)
