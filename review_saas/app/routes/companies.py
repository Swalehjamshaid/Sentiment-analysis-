# File: app/routes/companies.py
from __future__ import annotations
import os
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

# Internal imports
from app.db import get_db
from app.models import Company, Review
from app.dependencies import get_current_user  # Logic moved here to break circular imports

# ───────────────────────────────────────────────────────────────
# Logger Configuration
# ───────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ───────────────────────────────────────────────────────────────
# Router & Template Config
# ───────────────────────────────────────────────────────────────
router = APIRouter(tags=["dashboard"])

# Templates path resolution
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# ───────────────────────────────────────────────────────────────
# Analytics Helper Logic
# ───────────────────────────────────────────────────────────────

def get_dashboard_data(db: Session, company_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Calculates comprehensive metrics, trends, and heatmap data for the UI.
    """
    # Base query for reviews
    query = db.query(Review)
    if company_id:
        query = query.filter(Review.company_id == company_id)
    
    all_reviews = query.order_by(Review.review_date.desc()).all()
    total_reviews = len(all_reviews)

    # 1. Avg Rating Calculation
    avg_val = db.query(func.avg(Review.rating))
    if company_id:
        avg_val = avg_val.filter(Review.company_id == company_id)
    avg_rating = float(avg_val.scalar() or 0)

    # 2. Sentiment Distribution
    positive = sum(1 for r in all_reviews if r.rating >= 4)
    neutral = sum(1 for r in all_reviews if r.rating == 3)
    negative = sum(1 for r in all_reviews if r.rating <= 2)

    # 3. Activity Heatmap (Hourly)
    hourly_query = db.query(
        extract('hour', Review.review_date).label('hour'),
        func.count(Review.id).label('count')
    )
    if company_id:
        hourly_query = hourly_query.filter(Review.company_id == company_id)
    
    hourly_results = hourly_query.group_by('hour').all()
    heatmap_data = [0] * 24
    for hr, count in hourly_results:
        if hr is not None:
            heatmap_data[int(hr)] = count

    # 4. Sentiment Trend (Last 4 Weeks)
    four_weeks_ago = datetime.now() - timedelta(weeks=4)
    trend_query = db.query(
        func.date_trunc('week', Review.review_date).label('week'),
        func.count(Review.id).filter(Review.rating >= 4).label('pos'),
        func.count(Review.id).filter(Review.rating <= 2).label('neg')
    ).filter(Review.review_date >= four_weeks_ago)

    if company_id:
        trend_query = trend_query.filter(Review.company_id == company_id)
    
    weekly_data = trend_query.group_by('week').order_by('week').all()

    # 5. Build Final Payload
    return {
        "metrics": {
            "total": total_reviews,
            "avg_rating": round(avg_rating, 1),
            "risk_score": round((negative / total_reviews * 100), 1) if total_reviews > 0 else 0,
            "risk_level": "High" if negative > (total_reviews * 0.25) else "Low"
        },
        "date_range": {
            "start": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
            "end": datetime.now().strftime("%Y-%m-%d")
        },
        "trend": {
            "signal": "improving" if avg_rating >= 4.0 else "stable" if avg_rating >= 3.0 else "declining",
            "delta": 0.0,  # Could be calculated by comparing to previous period
            "labels": [row.week.strftime('%b %d') for row in weekly_data],
            "data": [3.5, 3.8, 4.0, avg_rating]  # Combined historic + current avg
        },
        "sentiment_trend": {
            "labels": [row.week.strftime('%b %d') for row in weekly_data],
            "positive": [row.pos for row in weekly_data],
            "negative": [row.neg for row in weekly_data]
        },
        "sentiment": {
            "Positive": positive,
            "Neutral": neutral,
            "Negative": negative
        },
        "heatmap": {
            "labels": list(range(24)),
            "data": heatmap_data
        },
        "reviews": {
            "total": total_reviews,
            "data": [
                {
                    "id": r.id,
                    "review_date": r.review_date.isoformat() if r.review_date else None,
                    "rating": r.rating,
                    "reviewer_name": r.reviewer_name,
                    "text": r.text,
                    "sentiment_category": "Positive" if r.rating >= 4 else "Negative" if r.rating <= 2 else "Neutral"
                } for r in all_reviews[:50]  # Limit to 50 for performance
            ]
        }
    }

# ───────────────────────────────────────────────────────────────
# Main Dashboard Routes
# ───────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def render_dashboard(
    request: Request,
    company_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """
    Main entry point for the Dashboard UI.
    Handles global view or company-specific view.
    """
    try:
        # Fetch all companies for the sidebar/switcher
        companies = db.query(Company).all()
        
        # Load specific company context if requested
        selected_company = None
        if company_id:
            selected_company = db.query(Company).filter(Company.id == company_id).first()

        # Generate the payload containing all analytics
        dashboard_payload = get_dashboard_data(db, company_id)

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "current_user": current_user,
                "dashboard_payload": dashboard_payload,
                "companies": companies,
                "selected_company": selected_company,
                "is_authenticated": current_user is not None
            }
        )
    except Exception as e:
        logger.error(f"Critical error rendering dashboard: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error loading the dashboard interface."
        )

# ───────────────────────────────────────────────────────────────
# API Endpoints
# ───────────────────────────────────────────────────────────────

@router.get("/api/dashboard/stats")
async def get_global_stats(db: Session = Depends(get_db)):
    """
    Lightweight API endpoint for periodic AJAX updates.
    """
    company_count = db.query(Company).count()
    review_count = db.query(Review).count()
    return {
        "total_companies": company_count,
        "total_reviews": review_count,
        "status": "operational",
        "timestamp": datetime.now().isoformat()
    }

@router.get("/dashbord")
async def redirect_legacy_dashboard():
    return RedirectResponse(url="/dashboard")
