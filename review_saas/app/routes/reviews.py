# filename: app/routes/reviews.py

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime

# Import your database models and scraper service
from app.db.database import get_db
from app.db import models
from app.services.scraper import fetch_reviews

router = APIRouter(prefix="/api/reviews", tags=["Reviews"])
logger = logging.getLogger(__name__)


@router.post("/ingest/{company_id}")
async def ingest_reviews(company_id: int, db: Session = Depends(get_db)):
    """
    Endpoint to trigger the Playwright scraper for a specific company.
    It fetches reviews from Google Maps and saves them to the Postgres database.
    """

    # 1. Verify Company Exists
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if not company.place_id:
        raise HTTPException(status_code=400, detail="Company missing Google Place ID")

    logger.info(f"🚀 Manual Sync Triggered for: {company.name} (ID: {company_id})")

    try:
        total_new_reviews = 0
        total_processed = 0
        skip = 0
        batch_size = 200
        MAX_BATCHES = 10  # safety limit (prevents infinite loop)

        for batch in range(MAX_BATCHES):
            logger.info(f"📦 Fetching batch {batch + 1} (skip={skip})")

            # 2. Call Scraper Service (batch of 200)
            scraped_data = await fetch_reviews(
                place_id=company.place_id,
                limit=batch_size,
                skip=skip
            )

            if not scraped_data:
                logger.info("✅ No more data available from scraper.")
                break

            new_count = 0

            # 3. Save to Database (Upsert Logic)
            for item in scraped_data:
                try:
                    existing = db.query(models.Review).filter(
                        models.Review.text == item["text"],
                        models.Review.author_name == item["author_name"],
                        models.Review.company_id == company_id
                    ).first()

                    if not existing:
                        new_review = models.Review(
                            company_id=company_id,
                            review_id=item["review_id"],
                            rating=item["rating"],
                            text=item["text"],
                            author_name=item["author_name"],
                            google_review_time=item["google_review_time"],
                            created_at=datetime.utcnow()
                        )
                        db.add(new_review)
                        new_count += 1

                except Exception:
                    continue

            db.commit()

            logger.info(f"✅ Batch {batch + 1}: {new_count} new reviews saved")

            total_new_reviews += new_count
            total_processed += len(scraped_data)

            # If less than batch size → no more data
            if len(scraped_data) < batch_size:
                logger.info("📭 Reached end of available reviews.")
                break

            skip += batch_size

        logger.info(f"🎯 Total new reviews added: {total_new_reviews}")

        return {
            "status": "success",
            "company": company.name,
            "reviews_count": total_new_reviews,
            "total_processed": total_processed
        }

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Ingestion Error for Company {company_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Scraper Error: {str(e)}"
        )


@router.get("/list/{company_id}", response_model=List[Dict[str, Any]])
async def get_company_reviews(company_id: int, db: Session = Depends(get_db)):
    """
    Returns all stored reviews for a specific company.
    """
    reviews = db.query(models.Review).filter(models.Review.company_id == company_id).all()
    return reviews
