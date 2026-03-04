# filename: app/routes/reviews.py

from __future__ import annotations
import logging
from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select
from datetime import datetime, timezone
from app.core.db import get_session
from app.core.models import Review, Company
from app.services.google_reviews import fetch_place_details

router = APIRouter(tags=['reviews'])
logger = logging.getLogger(__name__)

@router.get("/reviews")
async def get_company_reviews(company_id: int, page: int = 1, size: int = 20):
    async with get_session() as session:
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # 🚨 FIXED: Changed Review.review_time to Review.google_review_time
        result = await session.execute(
            select(Review)
            .where(Review.company_id == company_id)
            .order_by(Review.google_review_time.desc())
        )
        all_reviews = result.scalars().all()
        total = len(all_reviews)
        items = all_reviews[(page-1)*size:(page-1)*size+size]

        reviews_list = [
            {
                "author": r.author_name,
                "rating": r.rating,
                "text": r.text,
                # 🚨 FIXED: Changed r.review_time to r.google_review_time
                "time": r.google_review_time.isoformat() if r.google_review_time else None,
            }
            for r in items
        ]

    return {
        "success": True,
        "company": {"id": company.id, "name": company.name},
        "reviews": reviews_list,
        "total": total,
        "page": page,
        "size": size
    }

@router.get("/reviews/fetch_google")
async def fetch_google_place(place_id: str, company_id: int):
    async with get_session() as session:
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        try:
            details = fetch_place_details(place_id)
        except Exception as e:
            logger.error(f"Google fetch failed: {e}")
            raise HTTPException(status_code=500, detail=f"Google fetch failed: {e}")

        reviews = details.get("reviews", [])
        if not reviews:
            return {"success": True, "message": "No new reviews found", "stored": 0}

        stored_count = 0
        for r in reviews:
            # 🚨 FIXED: Mapping Google data to your model requirements
            g_id = r.get("reviewId") or f"{place_id}_{r.get('time', 0)}"
            
            # Format time correctly for Postgres
            if isinstance(r.get("time"), (int, float)):
                g_time = datetime.fromtimestamp(r["time"], tz=timezone.utc)
            else:
                g_time = datetime.now(timezone.utc)

            # 🚨 FIXED: Check existence using google_review_id (more accurate)
            exists = await session.execute(
                select(Review).where(Review.google_review_id == g_id)
            )
            if exists.scalar_one_or_none():
                continue

            # 🚨 FIXED: Using correct model field names
            new_review = Review(
                company_id=company_id,
                google_review_id=g_id,
                author_name=r.get("author_name"),
                rating=int(r.get("rating", 0)),
                text=r.get("text", ""),
                google_review_time=g_time, # Correct field
                profile_photo_url=r.get("profile_photo_url")
            )
            session.add(new_review)
            stored_count += 1

        await session.commit()
        logger.info(f"Stored {stored_count} new reviews for company_id={company_id}")

    return {"success": True, "stored": stored_count, "total_fetched": len(reviews)}
