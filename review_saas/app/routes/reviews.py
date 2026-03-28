# filename: app/routes/reviews.py
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import logging

# Internal imports
from app.core.db import get_session
from app.services.scraper import fetch_reviews

# Setup dedicated logging
logger = logging.getLogger("app.reviews")

router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.get("/ingest_all")
async def ingest_reviews_all(db: AsyncSession = Depends(get_session)):
    """
    GLOBAL INGEST TRIGGER
    Visit: https://your-project.up.railway.app/reviews/ingest_all
    """
    logger.info("🚀 GLOBAL INGEST START: Processing all companies...")

    # You can expand this list or later fetch from database
    COMPANIES = [
        {"id": 1, "name": "Gloria Jeans Coffees DHA Phase 5"},
        {"id": 4, "name": "E11EVEN MIAMI"},   # Add your other companies here
    ]

    results = []

    for company in COMPANIES:
        company_id = company["id"]
        company_name = company["name"]

        try:
            logger.info(f"🔍 Starting Ingest for: {company_name} (Company ID: {company_id})")

            # Call the updated hybrid scraper
            scraped_data = await fetch_reviews(
                company_id=company_id,
                session=db,
                place_id=company_name,      # Used as fallback
                limit=30                    # You can increase this
            )

            if not scraped_data:
                logger.warning(f"⚠️ No reviews returned for {company_name}")
                review_count = 0
            else:
                logger.info(f"✅ SUCCESS: Fetched {len(scraped_data)} reviews for {company_name}")
                review_count = len(scraped_data)

            results.append({
                "company_id": company_id,
                "company_name": company_name,
                "reviews_fetched": review_count,
                "status": "success" if review_count > 0 else "no_reviews"
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
        "message": "Global ingest process completed. Check logs for details.",
        "total_companies": len(COMPANIES),
        "results": results
    }


@router.post("/ingest/{company_id}")
async def ingest_single_company(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    """
    Ingest reviews for a single company by ID
    Example: POST /reviews/ingest/1
    """
    try:
        logger.info(f"🚀 Starting single ingest for Company ID: {company_id}")

        # Optional: Fetch company name for better logging
        from app.core.models import Company
        result = await db.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()

        company_name = company.name if company else f"Company-{company_id}"

        scraped_data = await fetch_reviews(
            company_id=company_id,
            session=db,
            place_id=company_name,
            limit=30
        )

        if not scraped_data:
            return {
                "status": "warning",
                "company_id": company_id,
                "company_name": company_name,
                "message": "No reviews were fetched. Check logs for details."
            }

        logger.info(f"✅ Successfully fetched {len(scraped_data)} reviews for {company_name}")

        return {
            "status": "success",
            "company_id": company_id,
            "company_name": company_name,
            "reviews_fetched": len(scraped_data),
            "message": "Reviews fetched successfully."
        }

    except Exception as e:
        logger.error(f"❌ Failed to ingest company {company_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{company_id}")
async def get_ingest_status(company_id: int):
    """Simple status check"""
    return {
        "company_id": company_id,
        "status": "Ready for ingest",
        "message": "Use /ingest/{company_id} or /ingest_all"
    }
