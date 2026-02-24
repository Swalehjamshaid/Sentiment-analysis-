from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from ..models import Company, Review, User
from .ai_insights import analyze_reviews, hour_heatmap
from .google_service import GoogleAPIService
from .multi_source_connector import MultiSourceConnector
from .alerts import AlertEngine
from .security import enforce_role_access

logger = logging.getLogger(__name__)

# ==========================================================
# ENTERPRISE DATE PARSER (Python 3.13 Safe)
# ==========================================================

def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        try:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None


# ==========================================================
# CENTRALIZED REAL-TIME SYNC ENGINE (Req 1,2,31)
# ==========================================================

async def sync_reviews(company: Company, db: Session) -> Dict[str, Any]:
    """
    Real-time review synchronization using centralized Google API layer.
    Supports scalable multi-source connectors.
    """
    google_service = GoogleAPIService(company)
    connector = MultiSourceConnector(company)

    try:
        # Google API sync
        google_status = await google_service.sync_reviews(db)

        # Future-proof multi-source sync
        extra_sources_status = await connector.sync_all(db)

        company.last_synced_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "google_status": google_status,
            "extra_sources": extra_sources_status,
            "sync_time": company.last_synced_at.isoformat()
        }

    except Exception as e:
        logger.exception("Sync failed")
        return {"error": str(e)}


# ==========================================================
# MAIN DASHBOARD ENGINE (Fulfills 31 Requirements)
# ==========================================================

async def dashboard_payload(
    db: Session,
    company_id: int,
    user: User,
    start: Optional[str] = None,
    end: Optional[str] = None
) -> Dict[str, Any]:

    # ------------------------------------------------------
    # 22. ROLE-BASED ACCESS CONTROL
    # ------------------------------------------------------
    enforce_role_access(user, company_id)

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return {}

    # ------------------------------------------------------
    # 31. GOOGLE API HEALTH CHECK
    # ------------------------------------------------------
    google_service = GoogleAPIService(company)
    api_health = await google_service.health_check()

    # ------------------------------------------------------
    # 2. REAL-TIME AUTO SYNC (optional trigger)
    # ------------------------------------------------------
    if api_health.get("healthy"):
        await sync_reviews(company, db)

    # ------------------------------------------------------
    # DATE FILTERING (Req 8)
    # ------------------------------------------------------
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)

    reviews_query = db.query(Review).filter(Review.company_id == company_id)

    if start_dt:
        reviews_query = reviews_query.filter(Review.review_date >= start_dt)
    if end_dt:
        reviews_query = reviews_query.filter(Review.review_date <= end_dt)

    reviews = reviews_query.all()

    # ------------------------------------------------------
    # CORE AI ENGINE (Req 3,4,5,6,10,21,24)
    # ------------------------------------------------------
    core = analyze_reviews(
        reviews=reviews,
        company=company,
        start=start_dt,
        end=end_dt,
        include_aspects=True,
        multi_language=True,
        predictive=True,
        anomaly_detection=True
    )

    # ------------------------------------------------------
    # 13. REVIEW VOLUME METRICS
    # ------------------------------------------------------
    volume_30d_start = datetime.now(timezone.utc) - timedelta(days=30)
    recent_reviews = [
        r for r in reviews if r.review_date and r.review_date >= volume_30d_start
    ]

    # ------------------------------------------------------
    # 9. RATING DISTRIBUTION
    # ------------------------------------------------------
    rating_distribution = {i: 0 for i in range(1, 6)}
    for r in reviews:
        rating_distribution[int(r.rating or 0)] += 1

    # ------------------------------------------------------
    # 26. RESPONSE TIME METRICS
    # ------------------------------------------------------
    responded_reviews = [r for r in reviews if r.response_date]
    avg_response_time = None
    if responded_reviews:
        total_time = sum(
            (r.response_date - r.review_date).total_seconds()
            for r in responded_reviews
            if r.review_date and r.response_date
        )
        avg_response_time = round(total_time / len(responded_reviews) / 3600, 2)

    # ------------------------------------------------------
    # 15 & 27 ALERT + ANOMALY ENGINE
    # ------------------------------------------------------
    alert_engine = AlertEngine()
    alerts = alert_engine.evaluate(core, reviews)

    # ------------------------------------------------------
    # 12 GEOGRAPHICAL INSIGHTS (if branches exist)
    # ------------------------------------------------------
    geo_data = core.get("geo_analysis", {})

    # ------------------------------------------------------
    # FINAL PAYLOAD
    # ------------------------------------------------------

    return {
        # 20 Executive Summary
        "executive_summary": core.get("executive_summary"),

        # 17 KPI Dashboard
        "kpis": {
            "avg_rating": core.get("avg_rating", 0),
            "sentiment_score": core.get("sentiment_score", 0),
            "risk_score": core.get("risk_score", 0),
            "review_growth_rate": core.get("growth_rate", 0),
            "avg_response_time_hours": avg_response_time,
        },

        # 7 Sentiment Trend
        "trend": core.get("trend"),

        # 9 Rating Distribution
        "rating_distribution": rating_distribution,

        # 6 Keywords & Topics
        "keywords": core.get("keywords"),

        # 5 Aspect-Based Sentiment
        "aspects": core.get("aspect_sentiment"),

        # 4 Emotion Layer
        "emotions": core.get("emotions"),

        # 11 Comparative Benchmarking
        "benchmark": core.get("benchmark"),

        # 12 Geographic Insights
        "geographical": geo_data,

        # 13 Volume Metrics
        "review_volume": {
            "total": len(reviews),
            "last_30_days": len(recent_reviews)
        },

        # 14 Response Monitoring
        "response_monitoring": {
            "responded": len(responded_reviews),
            "avg_response_time_hours": avg_response_time
        },

        # 15 Alerts
        "alerts": alerts,

        # 21 Predictive Forecast
        "forecast": core.get("forecast"),

        # 23 API Health
        "api_health": api_health,

        # 16 Drill Down Data
        "reviews": [
            {
                "id": r.id,
                "date": r.review_date.isoformat() if r.review_date else None,
                "rating": r.rating,
                "text": r.text,
                "sentiment": r.sentiment_category,
                "emotion": r.emotion_label,
                "aspects": r.aspect_data,
                "response_time_hours": (
                    round(
                        (r.response_date - r.review_date).total_seconds() / 3600, 2
                    )
                    if r.response_date and r.review_date
                    else None
                )
            }
            for r in reviews
        ],

        # 8 Date Window
        "window": {
            "start": start,
            "end": end
        },

        # 30 Cloud Scalable Metadata
        "meta": {
            "company_id": company.id,
            "last_synced": company.last_synced_at.isoformat()
            if company.last_synced_at else None,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    }
