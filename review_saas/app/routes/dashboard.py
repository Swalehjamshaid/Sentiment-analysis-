# File: app/routes/dashboard.py
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
# KEEP this prefix; include in main.py WITHOUT extra prefix
router = APIRouter(prefix='/dashboard', tags=['Dashboard'])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def dashboard_home(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user_companies = db.query(Company).filter(Company.owner_id == current_user.id).all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": current_user,  # used in greeting
        "companies": user_companies,
        "title": settings.APP_NAME,
        "google_maps_api_key": getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    })

# (KPIs endpoint kept as before)
@router.get('/kpis')
async def get_dashboard_kpis(
    company_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    base_query = db.query(Review).join(Company).filter(Company.owner_id == current_user.id)
    if company_id:
        base_query = base_query.filter(Review.company_id == company_id)

    all_reviews = base_query.all()
    total = len(all_reviews)
    ratings = [r.rating for r in all_reviews if r.rating is not None]
    avg_rating = round((sum(ratings) / len(ratings)) if ratings else 0.0, 2)

    pos = base_query.filter(Review.sentiment_category == 'Positive').count()
    neu = base_query.filter(Review.sentiment_category == 'Neutral').count()
    neg = base_query.filter(Review.sentiment_category == 'Negative').count()

    avg_sentiment_score_q = db.query(func.avg(Review.sentiment_score)).join(Company).filter(
        Company.owner_id == current_user.id
    )
    if company_id:
        avg_sentiment_score_q = avg_sentiment_score_q.filter(Review.company_id == company_id)
    final_score = avg_sentiment_score_q.scalar() or 0.0

    return {
        "total_reviews": total,
        "avg_rating": avg_rating,
        "sentiment": {
            "positive": pos, "neutral": neu, "negative": neg,
            "average_score": round(final_score, 4)
        },
        "status": "success"
    }
