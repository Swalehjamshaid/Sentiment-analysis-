# FILE: app/routes/dashboard.py

from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from datetime import datetime
import os

from ..db import get_db
from ..models import Company, Review

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


# ============================================================
# 1️⃣ RENDER DASHBOARD PAGE
# ============================================================

@router.get("/", name="dashboard")
@router.get("/{company_id}", name="dashboard_with_company")
async def get_dashboard(
    request: Request,
    company_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    initial_company = None

    if company_id:
        initial_company = db.query(Company).filter(Company.id == company_id).first()
        if not initial_company:
            raise HTTPException(status_code=404, detail="Company not found")

    maps_js_key = os.getenv("GOOGLE_MAPS_API_KEY")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "current_company_id": company_id or 0,
            "initial_company_name": initial_company.name if initial_company else None,
            "google_maps_api_key": maps_js_key,
        }
    )


# ============================================================
# 2️⃣ GET ALL COMPANIES (FOR DROPDOWN)
# ============================================================

@router.get("/api/companies")
def get_companies(db: Session = Depends(get_db)):
    return db.query(Company).filter(Company.status == "active").all()


# ============================================================
# 3️⃣ DASHBOARD METRICS (WITH DATE FILTER)
# ============================================================

@router.get("/api/metrics")
def get_dashboard_metrics(
    company_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
):

    query = db.query(Review).filter(Review.company_id == company_id)

    if start_date:
        query = query.filter(Review.created_at >= datetime.fromisoformat(start_date))
    if end_date:
        query = query.filter(Review.created_at <= datetime.fromisoformat(end_date))

    total_reviews = query.count()
    avg_rating = query.with_entities(func.avg(Review.rating)).scalar() or 0

    rating_distribution = (
        query.with_entities(Review.rating, func.count(Review.id))
        .group_by(Review.rating)
        .all()
    )

    return {
        "total_reviews": total_reviews,
        "average_rating": round(avg_rating, 2),
        "rating_distribution": {
            str(r[0]): r[1] for r in rating_distribution
        }
    }


# ============================================================
# 4️⃣ GET REVIEWS LIST
# ============================================================

@router.get("/api/reviews")
def get_reviews(
    company_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
):

    query = db.query(Review).filter(Review.company_id == company_id)

    if start_date:
        query = query.filter(Review.created_at >= datetime.fromisoformat(start_date))
    if end_date:
        query = query.filter(Review.created_at <= datetime.fromisoformat(end_date))

    reviews = query.order_by(Review.created_at.desc()).all()

    return reviews


# ============================================================
# 5️⃣ AI SUMMARY (ACTIONABLE INSIGHT)
# ============================================================

@router.get("/api/insights")
def get_ai_summary(company_id: int, db: Session = Depends(get_db)):

    reviews = (
        db.query(Review)
        .filter(Review.company_id == company_id)
        .all()
    )

    if not reviews:
        return {"summary": "No reviews available for analysis."}

    negative_reviews = [r for r in reviews if r.rating <= 2]

    summary = f"""
    Total Reviews: {len(reviews)}
    Negative Reviews: {len(negative_reviews)}
    
    Recommendation:
    Focus on improving customer service response time and address recurring
    complaints found in low-rated reviews.
    """

    return {"summary": summary.strip()}


# ============================================================
# 6️⃣ RECENT REPLIES
# ============================================================

@router.get("/api/recent-replies")
def get_recent_replies(company_id: int, db: Session = Depends(get_db)):

    reviews = (
        db.query(Review)
        .filter(
            Review.company_id == company_id,
            Review.reply_text.isnot(None)
        )
        .order_by(Review.reply_at.desc())
        .limit(10)
        .all()
    )

    return reviews
