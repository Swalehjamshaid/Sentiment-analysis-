import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from textblob import TextBlob

# Core imports
from app.core.db import get_session
from app.core import models
from app.services.scraper import fetch_reviews

logger = logging.getLogger("app.reviews")

router = APIRouter()

# =====================================================
# 🛠 HELPERS
# =====================================================
def calculate_sentiment(text: str) -> float:
    """Calculates polarity score (-1.0 to 1.0) for the dashboard charts."""
    if not text or text == "No content":
        return 0.0
    try:
        return round(TextBlob(text).sentiment.polarity, 2)
    except Exception:
        return 0.0

def _parse_date(date_str: str) -> datetime:
    """Standardizes date input for the database."""
    return datetime.utcnow()

# =====================================================
# 🚀 INGEST REVIEWS (SYNC BUTTON)
# =====================================================
@router.post("/reviews/ingest/{company_id}")
async def ingest_reviews(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    logger.info(f"🚀 Sync triggered for company_id={company_id}")

    # 1️⃣ Load company
    result = await db.execute(
        select(models.Company).where(models.Company.id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    logger.info(f"🏢 Company loaded: id={company.id}, name='{company.name}'")

    # 2️⃣ Fetch reviews from Scraper
    # Note: Scraper provides google_review_id, author_name, rating, text
    reviews_data = await fetch_reviews(
        company_id=company.id,
        name=company.name,
        session=db
    )

    if not reviews_data:
        logger.warning("⚠️ No reviews fetched from scraper")
        return {
            "status": "warning",
            "reviews_saved": 0
        }

    saved_count = 0

    # 3️⃣ Save reviews
    for r in reviews_data:
        # Extract the ID precisely as seen in your logs
        google_review_id = r.get("google_review_id")

        # Hard safety check to prevent empty records
        if not google_review_id or not str(google_review_id).strip():
            logger.warning(f"⚠️ Skipping review with missing google_review_id: {r.get('author_name')}")
            continue

        # Deduplication check
        existing = await db.execute(
            select(models.Review).where(
                models.Review.google_review_id == google_review_id
            )
        )
        if existing.scalar_one_or_none():
            continue

        # Logic: Perform Sentiment Analysis before saving
        # This is critical for the 'Customer Emotion Radar' and 'Sentiment Trend' in HTML
        text_content = r.get("text") or "No content"
        sentiment_score = calculate_sentiment(text_content)

        # Create the Review object
        review = models.Review(
            company_id=company.id,
            google_review_id=google_review_id,
            author_name=r.get("author_name", "Anonymous"),
            rating=int(r.get("rating", 0)),
            text=text_content,
            sentiment_score=sentiment_score, # Required for Chart.js
            source_platform="Google",
            first_seen_at=_parse_date(r.get("google_review_time")),
            # Pack likes/time into meta if your schema supports it
            meta={
                "likes": r.get("likes", 0),
                "google_time": r.get("google_review_time")
            }
        )

        db.add(review)
        saved_count += 1

    # Finalize the transaction
    if saved_count > 0:
        await db.commit()
    
    logger.info(f"✅ Sync complete | company: {company.name} | saved: {saved_count}")

    return {
        "status": "success",
        "reviews_saved": saved_count
    }
