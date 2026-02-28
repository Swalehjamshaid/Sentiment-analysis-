# filename: app/routes/dashboard.py
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..core.db import get_db
from ..core.security import get_current_user
from ..models.models import User, Company, Review

logger = logging.getLogger('app.dashboard')
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
        "companies": user_companies
    })

@router.get('/kpis')
async def get_dashboard_kpis(
    company_id: int | None = None, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """Requirement #141 & #142: Calculate KPIs and Sentiment Analytics."""
    
    # Requirement #42: Security check - Ensure user owns the company they are querying
    base_query = db.query(Review).join(Company).filter(Company.owner_id == current_user.id)
    
    if company_id:
        # Requirement #146: Filter data by specific company
        base_query = base_query.filter(Review.company_id == company_id)
    
    # Fetch all reviews for calculation
    all_reviews = base_query.all()
    total = len(all_reviews)
    
    # Requirement #141: Average Rating Calculation
    if total > 0:
        avg_rating = sum([r.rating for r in all_reviews if r.rating]) / total
    else:
        avg_rating = 0.0

    # Requirement #142: Sentiment Distribution
    pos = base_query.filter(Review.sentiment_category == 'Positive').count()
    neu = base_query.filter(Review.sentiment_category == 'Neutral').count()
    neg = base_query.filter(Review.sentiment_category == 'Negative').count()

    # Requirement #76: Sentiment Trend (Average Score)
    # Collect scores for the gauge/trend chart
    avg_sentiment_score = db.query(func.avg(Review.sentiment_score)).join(Company).filter(
        Company.owner_id == current_user.id
    )
    if company_id:
        avg_sentiment_score = avg_sentiment_score.filter(Review.company_id == company_id)
    
    final_score = avg_sentiment_score.scalar() or 0.0

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
