
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timezone

from app.db import get_db
from app import models, schemas
from app.services.rbac import get_current_user, require_roles

router = APIRouter(prefix="/api/reviews", tags=["Review Intelligence & Google Sync"])

def _parse_iso_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid date: {value}")

def _base_review_query(db: Session, company_id: int):
    return db.query(models.Review).filter(models.Review.company_id == company_id)

@router.get("/", response_model=schemas.ReviewListResponse)
def get_intelligent_reviews(
    company_id: int,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    emotion: Optional[str] = None,
    aspect: Optional[str] = None,
    sentiment: Optional[str] = None,
    language: Optional[str] = None,
    min_rating: Optional[int] = None,
    max_rating: Optional[int] = None,
    source: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))
):
    q = _base_review_query(db, company_id)
    sdt = _parse_iso_date(start_date); edt = _parse_iso_date(end_date)
    if sdt: q = q.filter(models.Review.review_date >= sdt)
    if edt: q = q.filter(models.Review.review_date <= edt)
    if emotion: q = q.filter(models.Review.emotion_label == emotion)
    if sentiment: q = q.filter(models.Review.sentiment_category == sentiment)
    if language: q = q.filter(models.Review.language == language)
    if source: q = q.filter(models.Review.source == source)
    if min_rating is not None: q = q.filter(models.Review.rating >= min_rating)
    if max_rating is not None: q = q.filter(models.Review.rating <= max_rating)
    if aspect:
        try:
            q = q.filter(models.Review.aspect_summary.has_key(aspect))  # type: ignore
        except Exception:
            pass

    total = q.count()
    offset = (page - 1) * limit
    rows: List[models.Review] = q.order_by(models.Review.review_date.desc()).offset(offset).limit(limit).all()

    # Convert to Pydantic-compatible objects
    out = []
    for r in rows:
        out.append(schemas.ReviewOut(
            id=r.id,
            company_id=r.company_id,
            source=r.source,
            external_id=r.external_id,
            text=r.text,
            rating=r.rating,
            review_date=r.review_date.isoformat() if r.review_date else None,
            reviewer_name=r.reviewer_name,
            sentiment_category=r.sentiment_category,
            sentiment_score=r.sentiment_score,
        ))

    return {"total": total, "page": page, "limit": limit, "data": out}
