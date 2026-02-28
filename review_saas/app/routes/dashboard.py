# File: review_saas/app/routes/dashboard.py
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..core.db import get_db
from ..core.security import get_current_user
from ..core.settings import settings
from ..models.models import User, Company, Review

logger = logging.getLogger('app.dashboard')

# IMPORTANT: This router ALREADY has '/dashboard' prefix.
# main.py must include it WITHOUT an extra prefix.
router = APIRouter(prefix='/dashboard', tags=['Dashboard'])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def dashboard_home(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Requirement #141: Main Dashboard View showing user's companies."""
    user_companies = db.query(Company).filter(Company.owner_id == current_user.id).all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": current_user,
        "companies": user_companies,
        "title": settings.APP_NAME,
        "google_maps_api_key": getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    })

@router.get('/kpis')
async def get_dashboard_kpis(
    company_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Requirement #141 & #142: Calculate KPIs and Sentiment Analytics."""
    # Security: ensure ownership
    base_query = db.query(Review).join(Company).filter(Company.owner_id == current_user.id)

    if company_id:
        base_query = base_query.filter(Review.company_id == company_id)

    all_reviews = base_query.all()
    total = len(all_reviews)

    # Average rating
    if total > 0:
        ratings = [r.rating for r in all_reviews if r.rating is not None]
        avg_rating = (sum(ratings) / len(ratings)) if ratings else 0.0
    else:
        avg_rating = 0.0

    # Sentiment counts
    pos = base_query.filter(Review.sentiment_category == 'Positive').count()
    neu = base_query.filter(Review.sentiment_category == 'Neutral').count()
    neg = base_query.filter(Review.sentiment_category == 'Negative').count()

    # Average sentiment score
    avg_sentiment_score_q = db.query(func.avg(Review.sentiment_score)).join(Company).filter(
        Company.owner_id == current_user.id
    )
    if company_id:
        avg_sentiment_score_q = avg_sentiment_score_q.filter(Review.company_id == company_id)

    final_score = avg_sentiment_score_q.scalar() or 0.0

    return {
        'total_reviews': total,
        'avg_rating': round(avg_rating, 2),
        'sentiment': {
            'positive': pos,
            'neutral': neu,
            'negative': neg,
            'average_score': round(final_score, 4)
        },
        'status': 'success'
    }

@router.get("/reviews", response_class=HTMLResponse)
async def dashboard_reviews(
    request: Request,
    company_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Requirement #143: Detailed Review List with AI Sentiment Labels."""
    query = db.query(Review).join(Company).filter(Company.owner_id == current_user.id)
    if company_id:
        query = query.filter(Review.company_id == company_id)

    reviews = query.order_by(Review.review_date.desc()).all()
    return templates.TemplateResponse("reviews_list.html", {
        "request": request,
        "reviews": reviews,
        "company_id": company_id
    })
