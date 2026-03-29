from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.services.scraper import ReviewScraper
from app.models.company import Company
from app.models.review import Review
from app.database import get_db
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

scraper = ReviewScraper()


@router.post("/reviews/ingest/{company_id}")
def ingest_reviews(company_id: int, db: Session = Depends(get_db)):

    try:
        logger.info(f"📥 Sync started for company_id: {company_id}")

        # ✅ STEP 1: Get company
        company = db.query(Company).filter(Company.id == company_id).first()

        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        if not company.place_id:
            raise HTTPException(status_code=400, detail="Missing place_id")

        # ✅ STEP 2: Fetch reviews
        result = scraper.fetch_reviews(company.place_id)
        reviews = result["reviews"]

        saved_count = 0

        # ✅ STEP 3: Save to DB (NO DUPLICATES)
        for r in reviews:

            exists = db.query(Review).filter(
                Review.company_id == company_id,
                Review.comment == r["comment"]
            ).first()

            if exists:
                continue

            new_review = Review(
                company_id=company_id,
                user=r["user"],
                rating=r["rating"],
                comment=r["comment"],
                date=r["date"]
            )

            db.add(new_review)
            saved_count += 1

        db.commit()

        return {
            "status": "success",
            "company_id": company_id,
            "reviews_fetched": len(reviews),
            "reviews_saved": saved_count
        }

    except Exception as e:
        logger.error(f"❌ Sync error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
