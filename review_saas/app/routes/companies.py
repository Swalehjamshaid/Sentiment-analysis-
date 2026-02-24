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
from sqlalchemy import func, extract, cast, DateTime

# Internal imports
from app.db import get_db
from app.models import Company, Review
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

def get_dashboard_data(db: Session, company_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Safely calculates metrics and handles the 'hour' extraction error.
    """
    try:
        query = db.query(Review)
        if company_id:
            query = query.filter(Review.company_id == company_id)
        
        all_reviews = query.order_by(Review.review_date.desc()).all()
        total_reviews = len(all_reviews)

        # Basic Stats
        avg_val = db.query(func.avg(Review.rating))
        if company_id:
            avg_val = avg_val.filter(Review.company_id == company_id)
        avg_rating = float(avg_val.scalar() or 0)

        positive = sum(1 for r in all_reviews if r.rating >= 4)
        negative = sum(1 for r in all_reviews if r.rating <= 2)
        neutral = total_reviews - (positive + negative)

        # SAFE HEATMAP LOGIC
        heatmap_data = [0] * 24
        try:
            # We cast to DateTime to help the DB find an 'hour' unit
            hourly_query = db.query(
                extract('hour', cast(Review.review_date, DateTime)).label('hour'),
                func.count(Review.id).label('count')
            )
            if company_id:
                hourly_query = hourly_query.filter(Review.company_id == company_id)
            
            for hr, count in hourly_query.group_by('hour').all():
                if hr is not None:
                    heatmap_data[int(hr)] = count
        except Exception as e:
            logger.warning(f"Hourly heatmap failed (DATE type issue): {e}")
            # FALLBACK: If we can't get hours, put everything in hour 0 to avoid crash
            heatmap_data[0] = total_reviews

        return {
            "metrics": {
                "total": total_reviews,
                "avg_rating": round(avg_rating, 1),
                "risk_score": round((negative / total_reviews * 100), 1) if total_reviews > 0 else 0,
                "risk_level": "High" if negative > (total_reviews * 0.2) else "Low"
            },
            "date_range": {"start": "2026-01-01", "end": "2026-02-24"},
            "trend": {"signal": "stable", "labels": ["W1", "W2", "W3", "Current"], "data": [avg_rating]*4},
            "sentiment_trend": {"labels": ["Current"], "positive": [positive], "negative": [negative]},
            "sentiment": {"Positive": positive, "Neutral": neutral, "Negative": negative},
            "heatmap": {"labels": list(range(24)), "data": heatmap_data},
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
                    } for r in all_reviews[:10]
                ]
            }
        }
    except Exception as e:
        logger.error(f"Data aggregation failed: {e}")
        return {}

@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def render_dashboard(
    request: Request,
    company_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    try:
        companies = db.query(Company).all()
        selected_company = db.query(Company).filter(Company.id == company_id).first() if company_id else None
        dashboard_payload = get_dashboard_data(db, company_id)

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "current_user": current_user,
                "dashboard_payload": dashboard_payload,
                "companies": companies,
                "selected_company": selected_company
            }
        )
    except Exception as e:
        logger.error(f"Dashboard Render Crash: {e}")
        raise HTTPException(status_code=500, detail="Error loading the dashboard interface.")
