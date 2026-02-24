# File: app/routes/companies.py
from __future__ import annotations
import os
import logging
import asyncio
import googlemaps
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, cast, DateTime

# Internal imports
from app.db import get_db
from app.models import Company, Review
from app.dependencies import get_current_user, manager # manager handles WebSockets

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# ───────────────────────────────────────────────────────────────
# Google API Fetching Logic (Background Task)
# ───────────────────────────────────────────────────────────────

def fetch_google_reviews(company_id: int, place_id: str, db_session_factory):
    """
    Background task to fetch reviews from Google Places API.
    Updates the 'last_synced_at' timestamp and broadcasts via WebSocket.
    """
    gmaps = googlemaps.Client(key=os.getenv("GOOGLE_MAPS_API_KEY"))
    db = db_session_factory()
    new_reviews_count = 0
    try:
        logger.info(f"Syncing reviews for Place ID: {place_id}")
        place_details = gmaps.place(place_id=place_id, fields=['reviews'])
        reviews_data = place_details.get('result', {}).get('reviews', [])
        
        for rev in reviews_data:
            # Prevent duplicates by checking reviewer name and text
            exists = db.query(Review).filter(
                Review.company_id == company_id,
                Review.reviewer_name == rev.get('author_name'),
                Review.text == rev.get('text')
            ).first()

            if not exists:
                new_review = Review(
                    company_id=company_id,
                    reviewer_name=rev.get('author_name'),
                    rating=rev.get('rating'),
                    text=rev.get('text'),
                    review_date=datetime.fromtimestamp(rev.get('time')),
                    sentiment_category="Positive" if rev.get('rating') >= 4 else "Negative" if rev.get('rating') <= 2 else "Neutral"
                )
                db.add(new_review)
                new_reviews_count += 1
        
        company = db.query(Company).filter(Company.id == company_id).first()
        if company:
            company.last_synced_at = datetime.now()
            
        db.commit()
        
        # Notify the frontend via WebSocket that new data is available
        if new_reviews_count > 0:
            asyncio.run(manager.broadcast({
                "type": "SYNC_COMPLETE",
                "company_id": company_id,
                "message": f"Added {new_reviews_count} new reviews!"
            }))
            
        logger.info(f"Sync complete for company {company_id}. New reviews: {new_reviews_count}")
    except Exception as e:
        logger.error(f"Google API Sync Error: {e}")
    finally:
        db.close()

# ───────────────────────────────────────────────────────────────
# Dashboard Analytics Helper
# ───────────────────────────────────────────────────────────────

def get_dashboard_data(db: Session, company_id: Optional[int] = None) -> Dict[str, Any]:
    try:
        query = db.query(Review)
        if company_id:
            query = query.filter(Review.company_id == company_id)
        
        all_reviews = query.order_by(Review.review_date.desc()).all()
        total_reviews = len(all_reviews)

        avg_val = db.query(func.avg(Review.rating))
        if company_id:
            avg_val = avg_val.filter(Review.company_id == company_id)
        avg_rating = float(avg_val.scalar() or 0)

        positive = sum(1 for r in all_reviews if r.rating >= 4)
        negative = sum(1 for r in all_reviews if r.rating <= 2)
        neutral = total_reviews - (positive + negative)

        heatmap_data = [0] * 24
        try:
            # Cast to DateTime handles PostgreSQL compatibility for DATE columns
            hourly_query = db.query(
                extract('hour', cast(Review.review_date, DateTime)).label('hour'),
                func.count(Review.id).label('count')
            )
            if company_id:
                hourly_query = hourly_query.filter(Review.company_id == company_id)
            for hr, count in hourly_query.group_by('hour').all():
                if hr is not None:
                    heatmap_data[int(hr)] = count
        except Exception:
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
                    } for r in all_reviews[:20]
                ]
            }
        }
    except Exception as e:
        logger.error(f"Dashboard Payload Error: {e}")
        return {}

# ───────────────────────────────────────────────────────────────
# Routes
# ───────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def render_dashboard(
    request: Request,
    background_tasks: BackgroundTasks,
    company_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    try:
        all_companies = db.query(Company).order_by(Company.name).all()
        selected_company = db.query(Company).filter(Company.id == company_id).first() if company_id else None
        
        # Auto-sync on page load if a company is selected
        if selected_company and selected_company.place_id:
            background_tasks.add_task(fetch_google_reviews, selected_company.id, selected_company.place_id, get_db)

        dashboard_payload = get_dashboard_data(db, company_id)

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "current_user": current_user,
                "dashboard_payload": dashboard_payload,
                "companies": all_companies,
                "selected_company": selected_company
            }
        )
    except Exception as e:
        logger.error(f"Dashboard Route Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/api/companies/{company_id}/sync")
async def sync_company_manual(
    company_id: int, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Manual sync trigger for the 'Sync Now' button."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company or not company.place_id:
        raise HTTPException(status_code=404, detail="Company Place ID missing")

    background_tasks.add_task(fetch_google_reviews, company.id, company.place_id, get_db)
    return {"status": "success", "message": "Manual sync started"}
