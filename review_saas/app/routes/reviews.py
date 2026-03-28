# filename: app/routes/reviews.py
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

# Internal imports
from app.core.db import get_session
from app.services.scraper import fetch_reviews
from app.core.models import Company   # Added for logging company name

logger = logging.getLogger("app.reviews")

router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.get("/ingest_all")
async def ingest_reviews_all(db: AsyncSession = Depends(get_session)):
    """
    Ingest reviews for all companies
    """
    logger.info("🚀 GLOBAL INGEST START: Processing all companies...")

    COMPANIES = [
        {"id": 1, "name": "Gloria Jeans Coffees DHA Phase 5"},
        {"id": 4, "name": "E11EVEN MIAMI"},
    ]

    results = []

    for company in COMPANIES:
        company_id = company["id"]
        company_name = company["name"]

        try:
            logger.info(f"🔍 Starting Ingest for: {company_name} (ID: {company_id})")

            scraped_data = await fetch_reviews(
                company_id=company_id,
                session=db,
                place_id=company_name,
                limit=30
            )

            review_count = len(scraped_data) if scraped_data else 0

            if review_count == 0:
                logger.warning(f"⚠️ No reviews returned for {company_name}")
                status = "no_reviews"
            else:
                logger.info(f"✅ Fetched {review_count} reviews for {company_name}")
                status = "success"

            results.append({
                "company_id": company_id,
                "company_name": company_name,
                "reviews_fetched": review_count,
                "status": status
            })

        except Exception as e:
            logger.error(f"❌ ERROR ingesting {company_name}: {str(e)}", exc_info=True)
            results.append({
                "company_id": company_id,
                "company_name": company_name,
                "error": str(e),
                "status": "failed"
            })

    logger.info(f"🏁 GLOBAL INGEST COMPLETE: Processed {len(COMPANIES)} companies.")
    
    return {
        "message": "Global ingest completed. Check logs for details.",
        "total_companies": len(COMPANIES),
        "results": results
    }


@router.post("/ingest/{company_id}")
async def ingest_single_company(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    """
    Ingest reviews for a single company
    Example: POST /reviews/ingest/1
    """
    try:
        logger.info(f"🚀 Starting single ingest for Company ID: {company_id}")

        # Get company name for better logging
        result = await db.execute(
            select(Company).where(Company.id == company_id)
        )
        company = result.scalar_one_or_none()
        company_name = company.name if company else f"Company-{company_id}"

        # Call scraper
        scraped_data = await fetch_reviews(
            company_id=company_id,
            session=db,
            place_id=company_name,
            limit=30
        )

        review_count = len(scraped_data) if scraped_data else 0

        if review_count == 0:
            return {
                "status": "warning",
                "company_id": company_id,
                "company_name": company_name,
                "reviews_fetched": 0,
                "message": "No reviews were fetched. Check scraper logs."
            }

        logger.info(f"✅ Successfully fetched {review_count} reviews for {company_name}")

        return {
            "status": "success",
            "company_id": company_id,
            "company_name": company_name,
            "reviews_fetched": review_count,
            "message": "Reviews fetched successfully."
        }

    except Exception as e:
        logger.error(f"❌ Failed to ingest company {company_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/status/{company_id}")
async def get_ingest_status(company_id: int):
    """Simple status check"""
    return {
        "company_id": company_id,
        "status": "ready",
        "message": "Use POST /reviews/ingest/{company_id} or GET /reviews/ingest_all"
    }
