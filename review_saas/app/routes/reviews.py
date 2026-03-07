# File: app/routes/reviews.py

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

# Ensure these paths match your actual directory structure
from app.db.session import get_db
from app.models.review import Review
from app.models.company import Company
from app.services.google_reviews import (
    ingest_company_reviews,
    OutscraperReviewsService
)

# Initialize router
router = APIRouter(prefix="/api/reviews", tags=["reviews"])

# Initialize Outscraper service
outscraper_service = OutscraperReviewsService()

# ---------------------------------------------------------
# Ingest reviews for a company from Google / Outscraper
# ---------------------------------------------------------
@router.post("/ingest/{place_id}/{company_id}")
async def ingest_reviews(
    place_id: str,
    company_id: int,
    limit: Optional[int] = Query(500, description="Max number of reviews"),
    db: Session = Depends(get_db)
):
    """
    Fetch reviews from Outscraper and store them in the database
    """
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        reviews_data = await outscraper_service.fetch_reviews(place_id, limit=limit)
        saved = 0

        for r in reviews_data:
            review_id = r.get("review_id")
            exists = db.query(Review).filter(
                Review.external_review_id == review_id
            ).first()

            if exists:
                continue

            review = Review(
                company_id=company_id,
                external_review_id=review_id,
                author=r.get("author_title"),
                rating=r.get("review_rating"),
                review_text=r.get("review_text"),
                review_date=r.get("review_datetime_utc"),
                sentiment=None
            )
            db.add(review)
            saved += 1

        db.commit()

        return {
            "status": "success",
            "reviews_fetched": len(reviews_data),
            "reviews_saved": saved
        }

    except Exception as e:
        db.rollback() # Good practice to rollback on error
        raise HTTPException(status_code=500, detail=f"Failed to ingest reviews: {str(e)}")


# ---------------------------------------------------------
# Fetch reviews for dashboard feed
# ---------------------------------------------------------
@router.get("/feed/{company_id}")
def get_reviews_feed(
    company_id: int,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    Fetch latest reviews for dashboard
    """
    reviews = (
        db.query(Review)
        .filter(Review.company_id == company_id)
        .order_by(Review.review_date.desc())
        .limit(limit)
        .all()
    )

    return {
        "status": "success",
        "reviews": [
            {
                "id": r.id,
                "author": r.author,
                "rating": r.rating,
                "text": r.review_text,
                "date": r.review_date,
                "sentiment": r.sentiment
            }
            for r in reviews
        ]
    }


# ---------------------------------------------------------
# Competitor analysis
# ---------------------------------------------------------
@router.post("/competitor-analysis")
async def competitor_analysis(
    queries: List[str],
    limit: Optional[int] = Query(200),
) -> Dict[str, Any]:
    """
    Fetch reviews for competitor businesses
    """
    try:
        all_data: Dict[str, List[Dict[str, Any]]] = {}
        for q in queries:
            reviews = await outscraper_service.fetch_reviews(q, limit=limit)
            all_data[q] = reviews

        return {"status": "success", "competitors": all_data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Competitor analysis failed: {str(e)}")


# ---------------------------------------------------------
# Get place details
# ---------------------------------------------------------
@router.get("/place-details/{place_id}")
async def fetch_place_details(place_id: str):
    """
    Fetch place details (sample review)
    """
    try:
        data = await outscraper_service.fetch_reviews(place_id, limit=1)
        return {"status": "success", "place_id": place_id, "sample_review": data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch place details: {str(e)}")


# ---------------------------------------------------------
# Review statistics for dashboard
# ---------------------------------------------------------
@router.get("/stats/{company_id}")
def review_stats(company_id: int, db: Session = Depends(get_db)):
    reviews = db.query(Review).filter(Review.company_id == company_id).all()
    total = len(reviews)
    if total == 0:
        return {"total_reviews": 0, "avg_rating": 0}

    # Added a small check for None ratings to prevent crashes
    valid_ratings = [r.rating for r in reviews if r.rating is not None]
    if not valid_ratings:
        return {"total_reviews": total, "avg_rating": 0}
        
    avg_rating = sum(valid_ratings) / len(valid_ratings)
    return {"total_reviews": total, "avg_rating": round(avg_rating, 2)}
