# filename: app/services/google_reviews.py
from __future__ import annotations
from typing import List
from datetime import datetime
import googlemaps
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.models import Company, Review
from app.core.config import settings

# ------------------------
# Fetch place details from Google Places API
# ------------------------
def fetch_place_details(place_id: str) -> dict:
    gmaps = googlemaps.Client(key=settings.GOOGLE_PLACES_API_KEY)
    try:
        details = gmaps.place(
            place_id=place_id,
            fields=['name','rating','user_ratings_total','reviews','formatted_address','website']
        )
        return details.get('result', {})
    except Exception as e:
        print(f"⚠️ Error fetching place details: {e}")
        return {}

def fetch_google_reviews(place_id: str, max_results: int = 50) -> List[dict]:
    details = fetch_place_details(place_id)
    reviews = details.get('reviews', [])
    return reviews[:max_results]

# ------------------------
# Ingest reviews into database
# ------------------------
async def ingest_company_reviews(session: AsyncSession, company_id: int, place_id: str):
    reviews_data = fetch_google_reviews(place_id)
    if not reviews_data:
        print(f"No reviews found for company_id={company_id}")
        return

    async with session.begin():
        result = await session.execute(select(Company).where(Company.id == company_id))
        company: Company = result.scalar_one_or_none()
        if not company:
            print(f"Company {company_id} not found in DB")
            return

        for r in reviews_data:
            source_id = f"{place_id}_{r.get('author_name','unknown')}_{r.get('time',0)}"
            existing = await session.execute(select(Review).where(Review.source_id == source_id))
            if existing.scalar_one_or_none():
                continue

            new_review = Review(
                company_id=company.id,
                source_id=source_id,
                author_name=r.get('author_name'),
                rating=int(r.get('rating', 0)),
                text=r.get('text'),
                review_time=datetime.fromtimestamp(r.get('time',0)),
            )
            session.add(new_review)

        await session.flush()
        all_reviews = await session.execute(select(Review).where(Review.company_id == company.id))
        all_reviews_list = all_reviews.scalars().all()
        if all_reviews_list:
            company.avg_rating = sum(r.rating for r in all_reviews_list)/len(all_reviews_list)
            company.review_count = len(all_reviews_list)
            company.last_updated = datetime.utcnow()
            session.add(company)

        print(f"✓ Ingested {len(reviews_data)} reviews for company {company.name}")
