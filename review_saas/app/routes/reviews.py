# filename: app/routes/reviews.py
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import logging

# Internal imports
from app.core.db import get_session
from app.services.scraper import fetch_reviews

# Setup dedicated logging for this router
logger = logging.getLogger("app.reviews")

# Define the router with the /reviews prefix
router = APIRouter(prefix="/reviews", tags=["Reviews"])

# In-memory company list for testing/initial ingest logic
COMPANIES = [
    {"id": 1, "name": "Villa The Grand Buffet"},
    {"id": 2, "name": "Bahria Town"}
]

@router.get("/ingest_all")
async def ingest_reviews(db: AsyncSession = Depends(get_session)):
    """
    GLOBAL INGEST TRIGGER:
    Visit: https://your-project.up.railway.app/reviews/ingest_all
    
    This calls the Hybrid Scraper (curl_cffi + AgentQL) for all listed companies.
    """
    logger.info("🚀 GLOBAL INGEST START: Processing all companies...")
    results = []

    for company in COMPANIES:
        company_id = company["id"]
        company_name = company["name"]

        try:
            logger.info(f"🔍 Starting Ingest for: {company_name} (ID: {company_id})")
            
            # ✅ Calls the 100% complete Hybrid Scraper
            # We pass the name into place_id to ensure AgentQL finds the right business
            scraped_data = await fetch_reviews(
                company_id=company_id, 
                session=db,
                place_id=company_name, 
                limit=50
            )

            if not scraped_data:
                logger.warning(f"⚠️ No reviews returned for {company_name}. Check ScrapeOps Proxy/AgentQL Key.")
                review_count = 0
            else:
                logger.info(f"✅ SUCCESS: Fetched {len(scraped_data)} reviews for {company_name}")
                review_count = len(scraped_data)

            results.append({
                "company_id": company_id,
                "company_name": company_name,
                "reviews_count": review_count,
                "status": "completed"
            })

        except Exception as e:
            logger.error(f"❌ CRITICAL ERROR for {company_name}: {str(e)}")
            results.append({
                "company_id": company_id,
                "company_name": company_name,
                "error": str(e),
                "status": "failed"
            })

    logger.info(f"🏁 GLOBAL INGEST COMPLETE: Processed {len(COMPANIES)} companies.")
    return {
        "message": "Ingest process finished. Check Railway logs for details.",
        "ingest_results": results
    }

@router.get("/status/{company_id}")
async def get_ingest_status(company_id: int):
    """Simple status check for a specific company."""
    return {"company_id": company_id, "status": "Ready for ingest"}
