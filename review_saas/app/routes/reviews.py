# FILE: app/routers/reviews.py
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Float
from typing import List, Optional
from datetime import datetime, timezone
import asyncio
import logging

from ..db import get_db
from .. import models, schemas

# --- Use module import for resilience (avoids symbol-resolve issues on startup) ---
from ..services import ai_insights

# --- Optional services: metrics & notifications; provide graceful fallbacks if missing ---
try:
    from ..services.google_api import GoogleAPIService, get_google_api_service  # type: ignore
except Exception:
    # Minimal safe stub to allow server boot if google_api is absent
    class GoogleAPIService:  # type: ignore
        async def fetch_reviews_async(self, place_id: str, page_token: Optional[str] = None):
            return {"reviews": [], "next_page_token": None, "recommended_backoff_sec": 0.5}
        def health_check(self, place_id: Optional[str]):
            return {"status": "not_configured"}
    def get_google_api_service() -> GoogleAPIService:  # type: ignore
        return GoogleAPIService()

try:
    from ..services.rbac import get_current_user, require_roles  # type: ignore
except Exception:
    # If RBAC service not wired yet, allow-all fallback for local boot
    def get_current_user():
        class _U: role = "owner"
        return _U()
    def require_roles(_roles):
        def _inner(user = Depends(get_current_user)):
            return None
        return _inner

# Metrics helpers (trends, distributions, correlation, etc.)
try:
    from ..services.metrics import (  # type: ignore
        aggregate_trends,
        aggregate_rating_distribution,
        compute_rating_sentiment_correlation,
        aggregate_benchmark,
        aggregate_geo_insights,
        compute_engagement_metrics,
        build_kpi_snapshot,
        build_executive_summary
    )
except Exception:
    # Safe no-op fallbacks so app can start if metrics module is missing
    def aggregate_trends(db, company_id, period, sdt, edt): return {"period": period, "buckets": []}
    def aggregate_rating_distribution(db, company_id, sdt, edt): return {"distribution": [], "total": 0}
    def compute_rating_sentiment_correlation(db, company_id, sdt, edt): return {"correlation": None, "n": 0}
    def aggregate_benchmark(db, company_ids, sdt, edt): return {"companies": []}
    def aggregate_geo_insights(db, company_id, group_by, sdt, edt): return {"grouping": group_by, "areas": []}
    def compute_engagement_metrics(db, company_id, sdt, edt): return {"review_count": 0, "responded_count": 0, "response_rate_percent": 0.0, "avg_response_time_hours": None}
    def build_kpi_snapshot(db, company_id, kpis, sdt, edt): return {"kpis": {k: None for k in kpis}}
    def build_executive_summary(db, company_id, sdt, edt): return {"summary": {"overall_sentiment": None, "rating_trend": [], "review_volume": [], "key_risks": [], "opportunities": []}}

# Export service (optional)
try:
    from ..services.exports import export_reviews_report  # type: ignore
except Exception:
    def export_reviews_report(db, company_id, fmt, sdt, edt):
        import io
        return io.BytesIO(b"no data"), f"reviews_{company_id}.txt", "text/plain"

# Notifications (optional)
try:
    from ..services.notifications import notify_alerts  # type: ignore
except Exception:
    def notify_alerts(*args, **kwargs):
        # Swallow if notification backend is not present
        return None

router = APIRouter(
    prefix="/api/reviews",
    tags=["Review Intelligence & Google Sync"]
)

log = logging.getLogger("reviews")
log.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────
# 0. Common helpers
# ─────────────────────────────────────────────────────────────

def _parse_iso_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Support 'YYYY-MM-DD' or full ISO; default to UTC
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {value}. Use ISO 8601 (e.g., 2025-12-31 or 2025-12-31T00:00:00Z).")

def _base_review_query(db: Session, company_id: int):
    return db.query(models.Review).filter(models.Review.company_id == company_id)

# ─────────────────────────────────────────────────────────────
# 1. Multi-Source + Google API Sync & Real-Time Ingestion (#1, #2, #23, #31)
# ─────────────────────────────────────────────────────────────

@router.post("/sync/{company_id}", status_code=status.HTTP_202_ACCEPTED)
async def sync_reviews(
    company_id: int,
    background_tasks: BackgroundTasks,
    source: str = Query("google", description="Data source: google|facebook|instagram|twitter|playstore|appstore|survey (google implemented)"),
    db: Session = Depends(get_db),
    api: GoogleAPIService = Depends(get_google_api_service),
    user = Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))  # #22 RBAC
):
    """
    #2: Real-Time Data Sync
    #1: Multi-Source (extensible)
    #23 & #31: Centralized API health, logging, rate limits, OAuth-ready
    """
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")

    if source == "google" and not getattr(company, "place_id", None):
        raise HTTPException(status_code=400, detail="Company Place ID missing for Google Sync.")

    async def _do_sync():
        sync_log = models.SyncLog(
            company_id=company_id,
            source=source,
            started_at=datetime.now(timezone.utc),
            status="running"
        )
        db.add(sync_log)
        db.commit()
        db.refresh(sync_log)

        try:
            new_count = 0
            page_token = None
            # Paginate/rate-limit aware loop
            while True:
                if source == "google":
                    batch = await api.fetch_reviews_async(place_id=company.place_id, page_token=page_token)
                else:
                    # Placeholder for other connectors – plug via service layer adapters
                    batch = {"reviews": [], "next_page_token": None, "recommended_backoff_sec": 0.5}

                reviews = batch.get("reviews", [])
                for r in reviews:
                    external_id = str(r.get("external_id"))
                    existing = db.query(models.Review).filter(
                        models.Review.company_id == company_id,
                        models.Review.source_type == source,
                        models.Review.external_id == external_id
                    ).first()

                    # Intelligence pipeline (#3 #4 #5 #6 #24 #25)
                    # Using module-level call for safety
                    if hasattr(ai_insights, "get_intelligence"):
                        # The version of get_intelligence may accept (text, rating, lang_hint) OR a list
                        try:
                            intel = ai_insights.get_intelligence(
                                text=r.get("text") or "",
                                rating=r.get("rating"),
                                lang_hint=r.get("language"),
                            )
                        except TypeError:
                            # Fallback to list-based interface if your ai_insights uses that
                            intel = ai_insights.get_intelligence([r])  # type: ignore
                    else:
                        # Minimal defaults if ai_insights is outdated
                        class _I: sentiment="Neutral"; confidence=0.0; emotion="Neutral"; aspects={}; topics=[]; lang="en"; journey_stage=None
                        intel = _I()

                    # Extract attributes safely
                    sentiment = getattr(intel, "sentiment", None) or (intel.get("analysis", {}).get("sentiment") if isinstance(intel, dict) else "Neutral")
                    confidence = getattr(intel, "confidence", None) or (intel.get("analysis", {}).get("confidence") if isinstance(intel, dict) else 0.0)
                    emotion = getattr(intel, "emotion", None) or "Neutral"
                    aspects = getattr(intel, "aspects", None) or {}
                    topics = getattr(intel, "topics", None) or []
                    language = getattr(intel, "lang", None) or r.get("language") or "en"
                    journey_stage = getattr(intel, "journey_stage", None)

                    if not existing:
                        obj = models.Review(
                            company_id=company_id,
                            external_id=external_id,
                            source_type=source,
                            reviewer_name=r.get("author_name"),
                            reviewer_profile_url=r.get("author_url"),
                            text=r.get("text"),
                            rating=r.get("rating"),
                            review_date=r.get("review_date") or datetime.now(timezone.utc),
                            sentiment_category=sentiment,     # Positive/Negative/Neutral
                            sentiment_score=confidence,       # confidence score
                            detected_emotion=emotion,         # #4
                            aspects=aspects,                   # #5 JSON {aspect: score or label}
                            topics=topics,                     # #6 keywords/topics
                            language=language,                 # #24
                            journey_stage=journey_stage        # #25
                        )
                        db.add(obj)
                        new_count += 1
                    else:
                        # If Google rating updated or text edited – keep in sync (#2)
                        existing.rating = r.get("rating", existing.rating)
                        existing.text = r.get("text", existing.text)
                        existing.review_date = r.get("review_date", existing.review_date)
                        existing.sentiment_category = sentiment
                        existing.sentiment_score = confidence
                        existing.detected_emotion = emotion
                        existing.aspects = aspects
                        existing.topics = topics
                        existing.language = language
                        existing.journey_stage = journey_stage

                db.commit()

                page_token = batch.get("next_page_token")
                if not page_token:
                    break
                # Respect backoff between pages if Google requires it
                await asyncio.sleep(batch.get("recommended_backoff_sec", 0.5))

            # Post-sync housekeeping
            company.last_synced_at = datetime.now(timezone.utc)
            company.sync_status = "OK"
            db.commit()

            # #27/#15 – detect anomalies and notify
            all_reviews = db.query(models.Review).filter_by(company_id=company_id).all()
            if hasattr(ai_insights, "detect_anomalies"):
                alerts = ai_insights.detect_anomalies(all_reviews)
            else:
                alerts = []
            if alerts:
                notify_alerts(company_id=company_id, alerts=alerts, db=db)

            # Finish log
            sync_log.finished_at = datetime.now(timezone.utc)
            sync_log.status = "success"
            sync_log.metrics = {"new_reviews_synced": new_count}
            db.commit()

        except Exception as e:
            log.exception("Sync failed")
            company.sync_status = "Failed"
            db.commit()
            sync_log.finished_at = datetime.now(timezone.utc)
            sync_log.status = "failed"
            sync_log.error_message = str(e)
            db.commit()

    # Run async in background for responsiveness
    background_tasks.add_task(asyncio.create_task, _do_sync())
    return {"status": "accepted", "message": "Sync started in background."}

# ─────────────────────────────────────────────────────────────
# 2. Advanced Filtering & Drill-Down (#8, #16, #24)
# ─────────────────────────────────────────────────────────────

@router.get("/", response_model=schemas.ReviewListResponse)
def get_intelligent_reviews(
    company_id: int,
    start_date: Optional[str] = Query(None, description="ISO date or datetime"),
    end_date: Optional[str] = Query(None, description="ISO date or datetime"),
    emotion: Optional[str] = None,
    aspect: Optional[str] = None,
    sentiment: Optional[str] = None,
    language: Optional[str] = None,
    min_rating: Optional[int] = None,
    max_rating: Optional[int] = None,
    source: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))
):
    query = _base_review_query(db, company_id)

    sdt = _parse_iso_date(start_date)
    edt = _parse_iso_date(end_date)
    if sdt: query = query.filter(models.Review.review_date >= sdt)
    if edt: query = query.filter(models.Review.review_date <= edt)
    if emotion: query = query.filter(models.Review.detected_emotion == emotion)
    if sentiment: query = query.filter(models.Review.sentiment_category == sentiment)
    if language: query = query.filter(models.Review.language == language)
    if source: query = query.filter(models.Review.source_type == source)
    if min_rating is not None: query = query.filter(models.Review.rating >= min_rating)
    if max_rating is not None: query = query.filter(models.Review.rating <= max_rating)

    # #5: Filter by JSON aspect key – PostgreSQL JSONB
    if aspect:
        query = query.filter(models.Review.aspects.has_key(aspect))  # type: ignore[attr-defined]

    total = query.count()
    reviews = query.order_by(models.Review.review_date.desc()).offset(offset).limit(limit).all()
    return {"total": total, "data": reviews}

# ─────────────────────────────────────────────────────────────
# 3. Trends, Distribution, Correlation, Volume (#7, #9, #10, #13)
# ─────────────────────────────────────────────────────────────

@router.get("/trends")
def get_trends(
    company_id: int,
    period: str = Query("daily", pattern="^(daily|weekly|monthly|quarterly)$"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))
):
    sdt = _parse_iso_date(start_date)
    edt = _parse_iso_date(end_date)
    return aggregate_trends(db, company_id, period, sdt, edt)

@router.get("/ratings/distribution")
def get_rating_distribution(
    company_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))
):
    sdt = _parse_iso_date(start_date)
    edt = _parse_iso_date(end_date)
    return aggregate_rating_distribution(db, company_id, sdt, edt)

@router.get("/correlation")
def get_correlation(
    company_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))
):
    sdt = _parse_iso_date(start_date)
    edt = _parse_iso_date(end_date)
    return compute_rating_sentiment_correlation(db, company_id, sdt, edt)

# ─────────────────────────────────────────────────────────────
# 4. Benchmarking, Geo Insights, KPIs, Executive Summary (#11, #12, #17, #20, #18 optional)
# ─────────────────────────────────────────────────────────────

@router.get("/benchmark")
def benchmark_companies(
    company_ids: List[int] = Query(..., description="IDs of own branches and/or competitors"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))
):
    sdt = _parse_iso_date(start_date)
    edt = _parse_iso_date(end_date)
    return aggregate_benchmark(db, company_ids, sdt, edt)

@router.get("/geo")
def get_geo_insights(
    company_id: int,
    group_by: str = Query("branch", pattern="^(branch|city|region)$"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))
):
    sdt = _parse_iso_date(start_date)
    edt = _parse_iso_date(end_date)
    return aggregate_geo_insights(db, company_id, group_by, sdt, edt)

@router.get("/kpis")
def kpi_dashboard(
    company_id: int,
    # owners can configure which KPIs to show (#17)
    kpis: List[str] = Query(
        default=["avg_rating", "sentiment_score", "review_count", "response_time", "review_growth"],
        description="KPI keys to include"
    ),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))
):
    sdt = _parse_iso_date(start_date)
    edt = _parse_iso_date(end_date)
    return build_kpi_snapshot(db, company_id, kpis, sdt, edt)

@router.get("/executive-summary")
def executive_summary(
    company_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))
):
    sdt = _parse_iso_date(start_date)
    edt = _parse_iso_date(end_date)
    return build_executive_summary(db, company_id, sdt, edt)

# ─────────────────────────────────────────────────────────────
# 5. Predictive Insights, Alerts, Engagement (#21, #15, #14, #26, #27)
# ─────────────────────────────────────────────────────────────

@router.get("/forecast")
def forecast(
    company_id: int,
    horizon_days: int = Query(30, ge=7, le=180),
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))
):
    # Your earlier router expected a DB-backed forecast function; gracefully fallback to ai_insights
    if hasattr(ai_insights, "forecast_sentiment_and_rating"):
        # If your ai_insights uses list-of-reviews interface:
        rows = db.query(models.Review).filter(models.Review.company_id == company_id).order_by(models.Review.review_date.asc()).all()
        # Convert to basic dicts expected by that function, if needed:
        simple = [{"rating": r.rating, "sentiment": r.sentiment_category, "text": r.text} for r in rows]
        try:
            return ai_insights.forecast_sentiment_and_rating(simple)
        except TypeError:
            # If it expects different signature, return minimal structure
            return ai_insights.forecast_sentiment_and_rating(rows)  # type: ignore
    return {"forecasted_rating": None, "forecasted_sentiment": {}}

@router.get("/alerts")
def get_alerts(
    company_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))
):
    alerts = (db.query(models.Alert)
                .filter_by(company_id=company_id)
                .order_by(models.Alert.created_at.desc())
                .limit(limit)
                .all())
    return {"total": len(alerts), "data": alerts}

@router.patch("/{review_id}/respond")
def update_response_status(
    review_id: int,
    response_text: Optional[str] = None,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager"]))
):
    """
    #14: Monitor business responses
    #26: Measure response time and effectiveness
    """
    review = db.query(models.Review).filter(models.Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    review.is_responded = True
    review.response_date = datetime.now(timezone.utc)
    review.response_text = response_text
    db.commit()
    return {"status": "Response tracked"}

@router.get("/engagement")
def get_engagement_metrics(
    company_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))
):
    sdt = _parse_iso_date(start_date)
    edt = _parse_iso_date(end_date)
    return compute_engagement_metrics(db, company_id, sdt, edt)

# ─────────────────────────────────────────────────────────────
# 6. Export & Reporting (#19)
# ─────────────────────────────────────────────────────────────

@router.get("/export")
def export_reports(
    company_id: int,
    format: str = Query("csv", pattern="^(csv|xlsx|pdf)$"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))
):
    sdt = _parse_iso_date(start_date)
    edt = _parse_iso_date(end_date)
    stream, filename, media_type = export_reviews_report(db, company_id, format, sdt, edt)
    return StreamingResponse(stream, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"'
    })

# ─────────────────────────────────────────────────────────────
# 7. API Health & Data Integrity (#23)
# ─────────────────────────────────────────────────────────────

@router.get("/health")
def api_health(
    company_id: int,
    db: Session = Depends(get_db),
    api: GoogleAPIService = Depends(get_google_api_service),
    user = Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))
):
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    google_status = api.health_check(place_id=getattr(company, "place_id", None)) if getattr(company, "place_id", None) else {"status": "no_place_id"}
    last_sync = db.query(models.SyncLog).filter_by(company_id=company_id).order_by(models.SyncLog.started_at.desc()).first()

    # Basic data integrity checks
    review_count = db.query(models.Review).filter_by(company_id=company_id).count()
    has_duplicates = db.query(models.Review.external_id)\
        .filter(models.Review.company_id == company_id)\
        .group_by(models.Review.external_id)\
        .having(func.count(models.Review.external_id) > 1).count() > 0

    return {
        "google_api": google_status,
        "last_sync": last_sync,
        "data_integrity": {
            "total_reviews": review_count,
            "duplicate_external_ids": has_duplicates
        }
    }
