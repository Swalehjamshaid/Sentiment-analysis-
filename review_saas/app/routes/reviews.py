from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.services.scraper import ReviewScraper
from app.models.company import Company   # make sure this exists
from app.database import get_db          # adjust if your path differs
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

scraper = ReviewScraper()


# =========================
# 🔥 SYNC REVIEWS (MAIN API)
# =========================
@router.post("/reviews/ingest/{company_id}")
def ingest_reviews(company_id: int, db: Session = Depends(get_db)):
    """
    Triggered by frontend Sync button
    """

    try:
        logger.info(f"📥 Sync started for company_id: {company_id}")

        # ✅ STEP 1: Get company from DB
        company = db.query(Company).filter(Company.id == company_id).first()

        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        if not company.place_id:
            raise HTTPException(status_code=400, detail="Place ID missing")

        # ✅ STEP 2: Fetch reviews via scraper
        result = scraper.fetch_reviews(company.place_id)

        reviews = result["reviews"]

        # ⚠️ OPTIONAL (future): Save reviews to DB here

        return {
            "status": "success",
            "company_id": company_id,
            "reviews_count": result["reviews_count"],
            "reviews": reviews
        }

    except HTTPException as he:
        raise he

    except Exception as e:
        logger.error(f"❌ Sync error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# 🧪 TEST API (OPTIONAL)
# =========================
@router.get("/reviews/test")
def test_reviews(place_id: str):
    """
    Direct test endpoint
    """
    try:
        result = scraper.fetch_reviews(place_id)

        return {
            "status": "success",
            "reviews_count": result["reviews_count"],
            "reviews": result["reviews"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
