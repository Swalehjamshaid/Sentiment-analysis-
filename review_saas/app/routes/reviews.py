# ==========================================================
# FILE: app/routes/reviews.py
# FULLY ALIGNED WITH YOUR scraper.py
# ==========================================================

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime

# ==========================================================
# DATABASE
# ==========================================================

from app.database import get_db

# ==========================================================
# MODELS
# ==========================================================

from app.models.company import Company
from app.models.review import Review

# ==========================================================
# SCRAPER
# ==========================================================

from app.scraper import scrape_google_reviews

# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter(
    prefix="/api/reviews",
    tags=["Reviews"]
)

# ==========================================================
# HEALTH
# ==========================================================

@router.get("/health")
async def health():

    return {
        "success": True,
        "message": "Review routes working"
    }

# ==========================================================
# SYNC REVIEWS
# ==========================================================

@router.post("/sync/{company_id}")
async def sync_reviews(
    company_id: int,
    db: Session = Depends(get_db)
):

    try:

        print("=" * 60)
        print(f"🚀 STARTING REVIEW SYNC => {company_id}")
        print("=" * 60)

        # ==================================================
        # GET COMPANY
        # ==================================================

        company = db.query(Company).filter(
            Company.id == company_id
        ).first()

        if not company:

            raise HTTPException(
                status_code=404,
                detail="Company not found"
            )

        print(f"✅ COMPANY => {company.name}")

        # ==================================================
        # PLACE ID CHECK
        # ==================================================

        if not company.place_id:

            raise HTTPException(
                status_code=400,
                detail="Missing Google Place ID"
            )

        print(f"✅ PLACE ID => {company.place_id}")

        # ==================================================
        # EXISTING IDS
        # ==================================================

        existing_reviews = db.query(
            Review.review_id
        ).filter(
            Review.company_id == company.id
        ).all()

        existing_ids = {
            r[0]
            for r in existing_reviews
            if r[0]
        }

        print(f"✅ EXISTING IDS => {len(existing_ids)}")

        # ==================================================
        # SCRAPE REVIEWS
        # ==================================================

        reviews = await scrape_google_reviews(
            place_id=company.place_id,
            existing_ids=existing_ids,
            target_limit=300
        )

        print(f"✅ SCRAPER RETURNED => {len(reviews)}")

        # ==================================================
        # EMPTY
        # ==================================================

        if not reviews:

            return {
                "success": False,
                "message": "No reviews found",
                "inserted_reviews": 0,
                "total_reviews": 0
            }

        inserted = 0
        failed = 0

        # ==================================================
        # SAVE REVIEWS
        # ==================================================

        for item in reviews:

            try:

                review_id = str(
                    item.get("review_id", "")
                ).strip()

                if not review_id:
                    failed += 1
                    continue

                # ==========================================
                # DUPLICATE CHECK
                # ==========================================

                existing = db.query(Review).filter(
                    Review.review_id == review_id
                ).first()

                if existing:
                    continue

                # ==========================================
                # DATA
                # ==========================================

                author = str(
                    item.get("author", "Anonymous")
                )[:255]

                text = str(
                    item.get("text", "")
                ).strip()

                rating = item.get("rating", 5)

                try:
                    rating = float(rating)
                except:
                    rating = 5.0

                review_date = item.get("date", "")

                # ==========================================
                # CREATE REVIEW
                # ==========================================

                new_review = Review(
                    company_id=company.id,
                    review_id=review_id,
                    author=author,
                    text=text,
                    rating=rating,
                    review_date=review_date,
                    source="Google"
                )

                db.add(new_review)

                inserted += 1

            except Exception as insert_error:

                print(
                    f"❌ INSERT ERROR => {insert_error}"
                )

                failed += 1

        # ==================================================
        # COMMIT
        # ==================================================

        db.commit()

        print("=" * 60)
        print(f"✅ INSERTED => {inserted}")
        print(f"❌ FAILED => {failed}")
        print("=" * 60)

        return {
            "success": True,
            "message": "Reviews synced successfully",
            "inserted_reviews": inserted,
            "failed_reviews": failed,
            "total_reviews": len(reviews)
        }

    except HTTPException:
        raise

    except Exception as e:

        db.rollback()

        print("=" * 60)
        print(f"❌ REVIEW SYNC ERROR => {e}")
        print("=" * 60)

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ==========================================================
# GET COMPANY REVIEWS
# ==========================================================

@router.get("/company/{company_id}")
async def get_company_reviews(
    company_id: int,
    db: Session = Depends(get_db)
):

    try:

        reviews = db.query(Review).filter(
            Review.company_id == company_id
        ).order_by(
            desc(Review.id)
        ).all()

        return reviews

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ==========================================================
# DELETE REVIEWS
# ==========================================================

@router.delete("/company/{company_id}")
async def delete_company_reviews(
    company_id: int,
    db: Session = Depends(get_db)
):

    try:

        deleted = db.query(Review).filter(
            Review.company_id == company_id
        ).delete()

        db.commit()

        return {
            "success": True,
            "deleted_reviews": deleted
        }

    except Exception as e:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
