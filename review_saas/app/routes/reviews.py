# FILE: app/routers/reviews.py
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
import googlemaps
from datetime import datetime, timezone

from ..db import get_db
from .. import models, schemas
from ..services.ai_insights import _get_intelligence, detect_anomalies
from ..services.analysis import dashboard_payload

router = APIRouter(
    prefix="/api/reviews",
    tags=["Review Intelligence & Google Sync"]
)

# ─────────────────────────────────────────────────────────────
# 1. Google API Sync & Real-Time Ingestion (#1, #2, #23)
# ─────────────────────────────────────────────────────────────

@router.post("/sync/{company_id}")
async def sync_google_reviews(
    company_id: int, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    """
    Requirement #2: Real-Time Data Sync.
    Requirement #23: API Health Monitoring.
    Triggers the Google Places API to fetch the latest reviews and run AI analysis.
    """
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company or not company.place_id:
        raise HTTPException(status_code=400, detail="Company Place ID missing for Google Sync.")

    # In a real production environment, the API Key would be in env vars
    gmaps = googlemaps.Client(key="YOUR_GOOGLE_MAPS_API_KEY")

    try:
        # Fetching reviews from Google
        place_details = gmaps.place(place_id=company.place_id, fields=['reviews'])
        google_reviews = place_details.get('result', {}).get('reviews', [])
        
        new_count = 0
        for gr in google_reviews:
            # Check if review already exists (#1 Scalability)
            existing = db.query(models.Review).filter(
                models.Review.external_id == gr['time'], # Google uses timestamp as ID in basic API
                models.Review.company_id == company_id
            ).first()

            if not existing:
                # Requirement #3, #4, #5: Run Intelligence Pipeline
                intel = _get_intelligence(gr.get('text', ''), gr.get('rating'))
                
                new_review = models.Review(
                    company_id=company_id,
                    external_id=str(gr['time']),
                    source_type="google",
                    reviewer_name=gr.get('author_name'),
                    text=gr.get('text'),
                    rating=gr.get('rating'),
                    review_date=datetime.fromtimestamp(gr['time'], tz=timezone.utc),
                    sentiment_category=intel['sentiment'],
                    sentiment_score=intel['confidence'],
                    detected_emotion=intel['emotion'],
                    aspects=intel['aspects'], # Stored as JSON (#5)
                    language=intel['lang']     # #24 Multi-language
                )
                db.add(new_review)
                new_count += 1
        
        company.last_synced_at = datetime.now(timezone.utc)
        db.commit()
        
        # Requirement #15: Trigger Anomaly Detection after sync
        alerts = detect_anomalies(db.query(models.Review).filter_by(company_id=company_id).all())
        
        return {"status": "success", "new_reviews_synced": new_count, "alerts": alerts}

    except Exception as e:
        # #23: Health Monitoring
        company.sync_status = "Failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Google API Health Error: {str(e)}")

# ─────────────────────────────────────────────────────────────
# 2. Advanced Filtering & Drill-Down (#8, #16)
# ─────────────────────────────────────────────────────────────

@router.get("/", response_model=schemas.ReviewListResponse)
def get_intelligent_reviews(
    company_id: int,
    # #8: Custom Date Range
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    # #16: Drill-Down Segments
    emotion: Optional[str] = None,
    aspect: Optional[str] = None,
    sentiment: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Handles dashboard 'Drill-Downs'. If a user clicks 'Frustration' in the chart,
    this endpoint filters the list to show only frustrating reviews.
    """
    query = db.query(models.Review).filter(models.Review.company_id == company_id)

    if start_date: query = query.filter(models.Review.review_date >= start_date)
    if end_date: query = query.filter(models.Review.review_date <= end_date)
    if emotion: query = query.filter(models.Review.detected_emotion == emotion)
    if sentiment: query = query.filter(models.Review.sentiment_category == sentiment)
    
    # #5: Filtering by JSON aspect (PostgreSQL syntax example)
    if aspect:
        query = query.filter(models.Review.aspects.has_key(aspect))

    reviews = query.order_by(models.Review.review_date.desc()).all()
    return {"total": len(reviews), "data": reviews}

# ─────────────────────────────────────────────────────────────
# 3. Engagement & Response Tracking (#14, #26)
# ─────────────────────────────────────────────────────────────

@router.patch("/{review_id}/respond")
def update_response_status(
    review_id: int, 
    db: Session = Depends(get_db)
):
    """
    Requirement #14: Monitoring if business responded.
    Requirement #26: Metrics for response time.
    """
    review = db.query(models.Review).filter(models.Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    review.is_responded = True
    review.response_date = datetime.now(timezone.utc)
    db.commit()
    return {"status": "Response tracked"}
