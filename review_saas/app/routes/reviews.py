import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, timezone

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.scraper import FastGoogleScraper
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
    Supports date filtering used by the dashboard 'Analyze' function.
    """
    stmt = select(Review).where(Review.company_id == company_id)
    
    # Apply date filters if provided by the dashboard UI
    if start:
        try:
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

    stmt = stmt.order_by(Review.google_review_time.desc())
    result = await session.execute(stmt)
    reviews = result.scalars().all()
    
    return reviews

# ----------------------------------------------------------------
# 2. POST ROUTE: Ingest New Reviews (High-Capacity Sync)
# ----------------------------------------------------------------
@router.post("/ingest/{company_id}")
async def ingest_reviews(
    company_id: int, 
    limit: int = 10000, # SET TO 10,000 PERMANENTLY
    session: AsyncSession = Depends(get_session)
):
    """
    Triggers the FastGoogleScraper to fetch live data and save to DB.
    Uses the google_id (0x...) to identify the business.
    """
    # 1. Verify Company and get Google ID (Feature ID)
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # CRITICAL: This is the 'address' the scraper needs
    data_id = company.google_id 
    if not data_id:
        logger.error(f"Missing google_id for company {company_id}")
        raise HTTPException(
            status_code=400, 
            detail="Error 400: This company is missing a Google ID (0x format). Please run the SQL patch."
        )

    # 2. Fetch data using the Fast Scraper
    logger.info(f"🚀 Starting ingestion for {company.name} (Limit: {limit})")
    scraped_data = await scraper.get_reviews(data_id=data_id, limit=limit)
    
    if not scraped_data:
        logger.warning(f"No data returned for {company.name}. Check if ID is valid.")
        return {"status": "success", "message": "No new reviews found or scraper blocked."}

    new_count = 0
    for item in scraped_data:
        # 3. Check if review already exists to avoid duplicates
        stmt = select(Review).where(
            and_(Review.company_id == company_id, Review.google_review_id == item["review_id"])
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        
        if not existing:
            # 4. Perform local Sentiment Analysis
            text_content = item["text"] if item["text"] else ""
            sentiment_score = analyzer.polarity_scores(text_content)["compound"]
            
            label = "Neutral"
            if sentiment_score > 0.05: label = "Positive"
            elif sentiment_score < -0.05: label = "Negative"

            # 5. Create Database Object 
            # Note: Using keys from the updated scraper.py (author_title, review_datetime_utc)
            new_review = Review(
                company_id=company_id,
                google_review_id=item["review_id"],
                author_name=item["author_title"],
                rating=item["rating"],
                text=text_content,
                google_review_time=datetime.fromisoformat(item["review_datetime_utc"]),
                sentiment_score=sentiment_score,
                sentiment_label=label,
                source_platform="Google"
            )
            session.add(new_review)
            new_count += 1

    # 6. Commit all changes
    try:
        await session.commit()
        logger.info(f"✅ Successfully added {new_count} new reviews for {company.name}")
    except Exception as e:
        await session.rollback()
        logger.error(f"Database Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save reviews")

    return {
        "status": "success",
        "company": company.name,
        "new_reviews_added": new_count,
        "total_scraped": len(scraped_data)
    }
