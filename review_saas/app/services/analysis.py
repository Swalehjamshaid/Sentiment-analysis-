# FILE: app/services/analysis.py
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from ..models import Company, Review
from .ai_insights import analyze_reviews, hour_heatmap

logger = logging.getLogger(__name__)

def _parse_date(value: Optional[str]) -> Optional[datetime]:
    """Ensures all date strings become UTC-aware to prevent Python 3.13 crashes."""
    if not value: return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        try:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

def dashboard_payload(db: Session, company_id: int, start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    """Assembles data for dashboard.html, ensuring no Null values crash the frontend."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company: return {}

    # Fetch all reviews to calculate stats
    reviews = db.query(Review).filter(Review.company_id == company_id).all()
    start_dt, end_dt = _parse_date(start), _parse_date(end)
    
    # Core AI Analysis
    core = analyze_reviews(reviews, company, start_dt, end_dt, include_aspects=True)

    # 30-Day Logic Aligned with Google API
    window_start = datetime.now(timezone.utc) - timedelta(days=30)
    recent_reviews = [r for r in reviews if r.review_date and r.review_date >= window_start]
    
    pos = sum(1 for r in recent_reviews if (r.rating or 0) >= 4)
    neg = sum(1 for r in recent_reviews if (r.rating or 0) <= 2)

    return {
        "company": {
            "id": company.id, 
            "name": company.name, 
            "last_synced": company.last_synced_at.isoformat() if company.last_synced_at else "Never"
        },
        "metrics": {
            "total": len(reviews),
            "avg_rating": core.get("avg_rating") or 0.0,
            "risk_score": core.get("risk_score") or 0.0,
            "risk_level": core.get("risk_level", "Low"),
        },
        "trend": {
            "signal": core.get("trend", {}).get("signal", "Stable"), 
            "delta": core.get("trend", {}).get("delta") or 0.0
        },
        "sentiment": core.get("sentiments", {"Positive": 0, "Neutral": 0, "Negative": 0}),
        "total_comments_30d": len(recent_reviews),
        "executive_summary_30d": {
            "executive_snapshot": f"Neural analysis of {len(recent_reviews)} recent Google reviews complete."
        },
        "sentiment_ring": {
            "labels": ["Pos", "Neg", "Neu"], 
            "data": [pos, neg, max(0, len(recent_reviews) - pos - neg)]
        },
        "reviews": {
            "data": [{
                "id": r.id,
                "review_date": r.review_date.isoformat() if r.review_date else None,
                "rating": int(r.rating or 0),
                "text": r.text or "No comment text provided.",
                "reviewer_name": r.reviewer_name or "Verified Customer",
                "sentiment_category": r.sentiment_category or "Neutral",
            } for r in reviews]
        },
        "window": {"start": start or "", "end": end or ""}
    }
