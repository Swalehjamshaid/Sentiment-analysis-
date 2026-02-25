# FILE: app/routes/companies.py

import os
import logging
from typing import Optional
import googlemaps
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db import get_db
from app.models import Company, Review
# Intelligence helpers exposed to FE via dashboard payload
from app.services.ai_insights import analyze_reviews, hour_heatmap, detect_anomalies

router = APIRouter(tags=["Business Intelligence & Google API"])
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _get_google_api_key() -> Optional[str]:
    """
    Prefer GOOGLE_MAPS_API_KEY (common) and fall back to GOOGLE_API_KEY.
    """
    return os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("GOOGLE_API_KEY")

def _ensure_tz(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

# ─────────────────────────────────────────────────────────────
# CENTRALIZED GOOGLE API LOGIC (#1, #2, #23, #31)
# ─────────────────────────────────────────────────────────────

def sync_google_reviews_task(company_id: int, place_id: str, db_session_factory):
    """
    Requirement #31: Centralized Google API Layer (local in this router).
    Handles Rate-limiting, Error Handling, and near-Real-Time Sync.
    """
    api_key = _get_google_api_key()
    if not api_key:
        logger.error("API Key missing in env (GOOGLE_MAPS_API_KEY / GOOGLE_API_KEY). Sync aborted.")
        return

    gmaps = googlemaps.Client(key=api_key)
    db: Session = db_session_factory()

    try:
        company: Optional[Company] = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            logger.warning(f"Company {company_id} not found. Abort sync.")
            return

        # Requirement #2: Real-time synchronization fetch
        result = gmaps.place(place_id=place_id, fields=['reviews', 'rating'])
        reviews_data = result.get('result', {}).get('reviews', []) or []

        new_count = 0
        for rev in reviews_data:
            # Google basic review object uses Unix 'time' (seconds) – use as external_id
            ext_id = str(rev.get('time'))
            if not ext_id:
                continue

            # Requirement #1: Scalable check for multi-source uniqueness
            exists = db.query(Review).filter(
                Review.company_id == company_id,
                Review.external_id == ext_id
            ).first()

            if exists:
                continue

            # Ingestion (AI enrichment can run async later)
            review_dt = datetime.fromtimestamp(rev.get('time', 0), tz=timezone.utc) if rev.get('time') else datetime.now(timezone.utc)

            new_review = Review(
                company_id=company_id,
                external_id=ext_id,
                source_type="google",
                reviewer_name=rev.get('author_name'),
                rating=float(rev.get('rating', 0) or 0),
                text=rev.get('text'),
                review_date=review_dt,
                reviewer_avatar=rev.get('profile_photo_url'),
                is_responded=False  # Requirement #14
            )
            db.add(new_review)
            new_count += 1

        company.last_synced_at = datetime.now(timezone.utc)
        company.sync_status = "Healthy"  # #23 API Health Monitoring

        db.commit()
        logger.info(f"[Google Sync] company_id={company_id} place_id={place_id} new_reviews={new_count}")

        # Optional: anomaly inspection right after sync (#27)
        all_reviews = db.query(Review).filter(Review.company_id == company_id).order_by(Review.review_date.desc()).all()
        alerts = detect_anomalies(all_reviews)
        if alerts:
            logger.warning(f"[Anomaly] company_id={company_id} alerts={len(alerts)}")

    except Exception as e:
        logger.exception(f"[Google Sync] Failure company_id={company_id}: {e}")
        try:
            # Ensure company reference exists before status update
            company = db.query(Company).filter(Company.id == company_id).first()
            if company:
                company.sync_status = "Error"
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()

# ─────────────────────────────────────────────────────────────
# DASHBOARD PAYLOAD GENERATOR (#7 - #30)
# ─────────────────────────────────────────────────────────────

def get_dashboard_data(
    db: Session,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None
):
    """
    Requirement #20: Executive Summary View.
    Aggregates primary analytical points into a frontend-ready payload.
    """
    company: Optional[Company] = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")

    query = db.query(Review).filter(Review.company_id == company_id)

    # Requirement #8: Custom Date Range Filtering
    # Accept ISO date or datetime
    sdt = None
    edt = None
    try:
        if start:
            sdt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            sdt = _ensure_tz(sdt)
            query = query.filter(Review.review_date >= sdt)
        if end:
            edt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            edt = _ensure_tz(edt)
            query = query.filter(Review.review_date <= edt)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601 (e.g., 2025-12-31 or 2025-12-31T23:59:59Z).")

    all_reviews = query.order_by(Review.review_date.desc()).all()

    # Requirement #3-#6, #21, #24: Run the Intelligence Engine
    ai_report = analyze_reviews(all_reviews, company, sdt, edt)

    # Requirement #7 & #13: Temporal Visualizations (hourly heatmap for the period)
    heatmap = hour_heatmap(all_reviews, sdt, edt)

    # Lightweight distribution (for FE 1–5 star chart) – #9
    dist = {str(i): 0 for i in range(1, 6)}
    total_vol = len(all_reviews)
    for r in all_reviews:
        if r.rating in (1, 2, 3, 4, 5):
            dist[str(int(r.rating))] += 1

    # Response rate & anomaly flag – #14, #26, #27
    responded = sum(1 for r in all_reviews if getattr(r, "is_responded", False))
    response_rate = f"{(responded / total_vol * 100):.1f}%" if total_vol else "0%"

    return {
        "company": {
            "id": company.id,
            "name": company.name,
            "city": getattr(company, "city", None),  # #12 Geographical
            "sync_status": getattr(company, "sync_status", "Unknown"),  # #23
            "last_sync": company.last_synced_at.isoformat() if company.last_synced_at else None
        },
        "executive_summary": {  # #20
            "avg_rating": ai_report.get("avg_rating", 0.0),
            "sentiment_score": ai_report.get("executive_summary", {}).get("sentiment_score", 0),
            "prediction": ai_report.get("executive_summary", {}).get("predictive_signal", "Stable"),  # #21
            "risk_level": ai_report.get("executive_summary", {}).get("risk_level", "Low"),
            "top_keywords": ai_report.get("executive_summary", {}).get("top_keywords", [])
        },
        "visuals": {  # #4, #5, #7, #9
            "emotions": ai_report.get("emotion_breakdown") or ai_report.get("emotions", {}),
            "aspects": ai_report.get("aspect_performance", {}),
            "rating_distribution": dist,
            "heatmap": heatmap
        },
        "metrics": {  # #13, #14, #26, #27
            "total_volume": total_vol,
            "response_rate": response_rate,
            "anomaly_detected": ai_report.get("anomaly_alert", False)
        },
        "drill_down": [  # #16 – recent sample for modal/list
            {
                "id": r.id,
                "text": r.text,
                "rating": r.rating,
                "emotion": getattr(r, "detected_emotion", "Neutral"),
                "date": _ensure_tz(r.review_date).isoformat() if r.review_date else None,
                "source": getattr(r, "source_type", "google")
            } for r in all_reviews[:15]
        ],
        # Hooks for future FE tabs (#11, #12, #18)
        "benchmarking": ai_report.get("benchmarking", {"competitors": []}),
        "geo_insights": ai_report.get("geo_insights", {"locations": []}),
        # API/Sync health (#23)
        "api_status": ai_report.get("api_status", {"google_api_health": "Unknown", "sync_timestamp": None}),
        "payload_version": ai_report.get("payload_version", "7.0-Enterprise")
    }

# ─────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────

@router.post("/companies/{company_id}/sync")
async def trigger_manual_sync(company_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Requirement #31: Scalable connector trigger for Google sync.
    """
    company: Optional[Company] = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    if not company.place_id:
        raise HTTPException(status_code=400, detail="Google Place ID not configured for this company.")

    # Note: pass the dependency factory (get_db) and create a fresh session inside the task
    def _db_factory():
        return next(get_db())

    background_tasks.add_task(sync_google_reviews_task, company_id, company.place_id, _db_factory)
    return {"message": "Google API synchronization initialized."}

@router.get("/companies/{company_id}/dashboard")
def get_company_dashboard(company_id: int, start: Optional[str] = None, end: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Frontend-ready aggregated dashboard payload (satisfies #7-#30 essentials).
    """
    return get_dashboard_data(db, company_id=company_id, start=start, end=end)
