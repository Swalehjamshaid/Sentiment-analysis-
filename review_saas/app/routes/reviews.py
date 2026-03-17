# filename: app/routes/reviews.py
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, timezone

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.scraper_service import FastGoogleScraper
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

router = APIRouter(prefix="/api/reviews", tags=["reviews"])
logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()
scraper = FastGoogleScraper()

# ----------------------------------------------------------------
# 1. GET ROUTE: List/Count Reviews (Date-Wise Filtering)
# ----------------------------------------------------------------
@router.get("/")
async def get_reviews(
    company_id: int = Query(...),
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    """
    Fetches stored reviews from the database for a specific company.
    Supports precise date filtering to update dashboard KPIs and charts.
    """
    stmt = select(Review).where(Review.company_id == company_id)
    
    # Apply date filters provided by the dashboard UI
    if start:
        try:
            # Handle standard 'YYYY-MM-DD' and ISO formats
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            stmt = stmt.where(Review.google_review_time >= start_dt)
        except ValueError:
            logger.warning(f"Invalid start date format: {start}")

    if end:
        try:
            end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            stmt = stmt.where(Review.google_review_time <= end_dt)
        except ValueError:
            logger.warning(f"Invalid end date format: {end}")

    # Order by newest first for trend accuracy
    stmt = stmt.order_by(Review.google_review_time.desc())
    
    result = await session.execute(stmt)
    reviews = result.scalars().all()
    
    return reviews

# ----------------------------------------------------------------
# 2. POST ROUTE: Ingest New Reviews (High-Capacity Date-Sync)
# ----------------------------------------------------------------
@router.post("/ingest/{company_id}")
async def ingest_reviews(
    company_id: int, 
    limit: int = 1000, 
    session: AsyncSession = Depends(get_session)
):
    """
    Triggers the FastGoogleScraper to fetch live data.
    Increased limit to 1000 to pull historical data beyond the 250 limit.
    """
    # 1. Verify Company and get Google Data ID
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    data_id = company.google_id 
    if not data_id:
        logger.error(f"Missing google_id for company {company_id}")
        raise HTTPException(
            status_code=400, 
            detail="Company does not have a valid Google Data ID (Feature ID) in the database."
        )

    # 2. Fetch data using the Fast Scraper (Mimics Google Internal API)
    logger.info(f"🚀 Starting date-wise ingestion for {company.name} (Limit: {limit})")
    scraped_data = await scraper.get_reviews(data_id=data_id, limit=limit)
    
    if not scraped_data:
        return {"status": "success", "message": "No new reviews found or scraper blocked."}

    new_count = 0
    for item in scraped_data:
        # 3. Duplicate Prevention
        stmt = select(Review).where(Review.google_review_id == item["review_id"])
        existing = (await session.execute(stmt)).scalar_one_or_none()
        
        if not existing:
            # 4. Sentiment Analysis (Free/Local)
            text_content = item["text"] if item["text"] else ""
            sentiment_results = analyzer.polarity_scores(text_content)
            sentiment_score = sentiment_results["compound"]
            
            label = "Neutral"
            if sentiment_score > 0.05: label = "Positive"
            elif sentiment_score < -0.05: label = "Negative"

            # 5. Timestamp Normalization
            review_time = datetime.fromisoformat(item["review_datetime_utc"])
            if review_time.tzinfo is None:
                review_time = review_time.replace(tzinfo=timezone.utc)

            # 6. Database Object Creation
            new_review = Review(
                company_id=company_id,
                google_review_id=item["review_id"],
                author_name=item["author_title"],
                rating=item["rating"],
                text=text_content,
                google_review_time=review_time,
                sentiment_score=sentiment_score,
                sentiment_label=label
            )
            session.add(new_review)
            new_count += 1

    # 7. Persist to Postgres
    try:
        await session.commit()
        logger.info(f"✅ Ingestion Complete: {new_count} records added.")
    except Exception as e:
        await session.rollback()
        logger.error(f"Database Error: {e}")
        raise HTTPException(status_code=500, detail="Persistence failure")

    return {
        "status": "success",
        "company": company.name,
        "new_reviews_added": new_count,
        "total_scraped": len(scraped_data)
    }

# ----------------------------------------------------------------
# 3. AI SUMMARY ROUTE: Date-Wise Sentiment Insights
# ----------------------------------------------------------------
@router.get("/summary")
async def get_date_wise_summary(
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    """
    Returns an AI-ready summary of reviews filtered by date.
    This informs the 'AI Insight Layer' on the dashboard.
    """
    # Reuse the logic from the GET reviews route
    reviews = await get_reviews(company_id, start, end, session)
    
    if not reviews:
        return {"summary": "No data available for the selected period.", "label": "N/A"}

    # Basic aggregate logic for the AI layer
    avg_rating = sum([r.rating for r in reviews]) / len(reviews)
    pos_count = len([r for r in reviews if r.sentiment_label == "Positive"])
    
    return {
        "total_count": len(reviews),
        "average_rating": round(avg_rating, 2),
        "positive_percentage": round((pos_count / len(reviews)) * 100, 2),
        "time_period": f"{start or 'Beginning'} to {end or 'Now'}"
    }
