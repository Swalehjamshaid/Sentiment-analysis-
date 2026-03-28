from fastapi import APIRouter, HTTPException
from app.services.scraper import fetch_reviews
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Example in-memory DB for companies
COMPANIES = [
    {"id": 1, "name": "Villa The Grand Buffet"},
    {"id": 2, "name": "Bahria Town"}
]

@router.post("/ingest_reviews")
async def ingest_reviews():
    """
    Ingest reviews for all companies asynchronously using scraper.py
    """
    results = []

    for company in COMPANIES:
        company_id = company["id"]
        company_name = company["name"]

        try:
            # ✅ Async call to scraper
            scraped_data = await fetch_reviews(name=company_name, limit=300)

            if not scraped_data:
                logger.info(f"ℹ️ No reviews returned for {company_name}")
            else:
                logger.info(f"✅ Fetched {len(scraped_data)} reviews for {company_name}")

            results.append({
                "company_id": company_id,
                "company_name": company_name,
                "reviews_count": len(scraped_data),
                "reviews": scraped_data
            })

        except Exception as e:
            logger.error(f"❌ Ingest error for company {company_id} ({company_name}): {e}")
            results.append({
                "company_id": company_id,
                "company_name": company_name,
                "error": str(e)
            })

    return {"ingest_results": results}
