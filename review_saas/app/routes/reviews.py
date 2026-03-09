# filename: app/routes/reviews.py
from __future__ import annotations

from typing import List, Optional, Dict, Any, Tuple
from collections import Counter
from datetime import datetime, timedelta, date, time

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.db import get_session
from app.core.models import Review, Company
from app.services.google_reviews import OutscraperReviewsService, ReviewData

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------
DEFAULT_DAYS = 30
router = APIRouter(prefix="/api/reviews", tags=["reviews"])

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def _normalize_window(start_date: Optional[str], end_date: Optional[str]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Accepts YYYY-MM-DD or ISO8601 strings and returns (start_dt, end_dt) inclusive.
    Defaults to last 30 days if both missing.
    """
    def _parse(s: Optional[str]) -> Optional[datetime]:
        if not s:
            return None
        try:
            if len(s) == 10:
                return datetime.strptime(s, "%Y-%m-%d")
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    s = _parse(start_date)
    e = _parse(end_date)

    if not s and not e:
        e = datetime.combine(date.today(), datetime.max.time())
        s = e - timedelta(days=DEFAULT_DAYS - 1)
    if s and not e:
        e = datetime.combine(date.today(), datetime.max.time())
    if e and not s:
        s = e - timedelta(days=DEFAULT_DAYS - 1)

    if s and s.tzinfo:
        s = s.replace(tzinfo=None)
    if e and e.tzinfo:
        e = e.replace(tzinfo=None)

    if s:
        s = datetime.combine(s.date(), time.min)
    if e:
        e = datetime.combine(e.date(), time.max)

    if s and e and s > e:
        s, e = e, s

    return s, e

def _set_if_has(obj: Any, field: str, value: Any):
    if hasattr(obj, field):
        setattr(obj, field, value)

def _reviews_client(request: Request):
    client = getattr(request.app.state, "google_reviews_client", None)
    if client is None:
        raise HTTPException(status_code=501, detail="Reviews API client not configured (app.state.google_reviews_client)")
    return client

def _resolve_date_col():
    """
    Choose best datetime column: google_review_time > review_date > created_at > id
    """
    if hasattr(Review, "google_review_time"):
        return getattr(Review, "google_review_time")
    if hasattr(Review, "review_date"):
        return getattr(Review, "review_date")
    if hasattr(Review, "created_at"):
        return getattr(Review, "created_at")
    return getattr(Review, "id")

# ---------------------------------------------------------
# /list Endpoint
# ---------------------------------------------------------
@router.get("/list")
async def list_reviews(
    company_id: int = Query(..., description="Company ID"),
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    sort: Optional[str] = Query("newest", regex="^(newest|oldest|highest|lowest)$"),
    limit: int = Query(200, ge=10, le=2000),
    db: AsyncSession = Depends(get_session),
):
    s, e = _normalize_window(start, end)
    date_col = _resolve_date_col()

    # Sorting logic
    if sort == "oldest":
        order_by = [date_col.asc()]
    elif sort == "highest":
        order_by = [getattr(Review, "rating").desc(), date_col.desc()] if hasattr(Review, "rating") else [date_col.desc()]
    elif sort == "lowest":
        order_by = [getattr(Review, "rating").asc(), date_col.desc()] if hasattr(Review, "rating") else [date_col.desc()]
    else:
        order_by = [date_col.desc()]

    q = select(Review).where(Review.company_id == company_id)
    if s:
        q = q.where(date_col >= s)
    if e:
        q = q.where(date_col <= e)
    q = q.order_by(*order_by).limit(limit)

    result = await db.execute(q)
    rows = result.scalars().all()

    def _fmt_date(dt_obj) -> str:
        if not dt_obj:
            return ""
        try:
            if isinstance(dt_obj, datetime):
                return dt_obj.strftime("%Y-%m-%d")
            return str(dt_obj)[:10]
        except Exception:
            return str(dt_obj)

    items = []
    for r in rows:
        author_name = getattr(r, "author_name", None) or getattr(r, "author", None) or "Anonymous"
        text = getattr(r, "text", None) or getattr(r, "review_text", None) or ""
        dt_obj = getattr(r, "google_review_time", None) or getattr(r, "review_date", None) or getattr(r, "created_at", None)
        rating = getattr(r, "rating", None)

        items.append({
            "author_name": author_name,
            "rating": rating,
            "text": text,
            "review_time": _fmt_date(dt_obj),
            "profile_photo_url": getattr(r, "profile_photo_url", None) or "",
        })

    return {"items": items}

# ---------------------------------------------------------
# /ingest Endpoint
# ---------------------------------------------------------
@router.post("/ingest")
async def ingest_reviews(
    request: Request,
    place_id: str,
    company_id: int,
    competitor_place_ids: Optional[List[str]] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=50000),
    db: AsyncSession = Depends(get_session),
):
    try:
        # Validate company
        result = await db.execute(select(Company).filter(Company.id == company_id))
        company = result.scalars().first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        start_dt, end_dt = _normalize_window(start_date, end_date)

        entities: List[str] = [place_id]
        if competitor_place_ids:
            entities.extend([pid for pid in competitor_place_ids if pid])

        client = _reviews_client(request)
        service = OutscraperReviewsService(client)

        total_saved = 0
        total_fetched = 0

        for pid in entities:
            reviews_data: List[ReviewData] = service.fetch_reviews(
                place_id=pid,
                start_date=start_dt,
                end_date=end_dt,
                max_reviews=limit,
            )
            total_fetched += len(reviews_data)

            for r in reviews_data:
                review_date = r.time_created

                external_id_field = "external_review_id" if hasattr(Review, "external_review_id") else None

                if external_id_field:
                    exist = await db.execute(
                        select(Review).filter(getattr(Review, external_id_field) == r.review_id)
                    )
                    if exist.scalars().first():
                        continue
                else:
                    exist = await db.execute(
                        select(Review).filter(
                            and_(
                                Review.company_id == company_id,
                                Review.author_name == r.author_name,
                                Review.google_review_time == review_date,
                            )
                        )
                    )
                    if exist.scalars().first():
                        continue

                model = Review()
                _set_if_has(model, "company_id", company_id)
                _set_if_has(model, "external_review_id", r.review_id)
                _set_if_has(model, "google_review_id", r.review_id)
                _set_if_has(model, "author_name", r.author_name)
                _set_if_has(model, "author", r.author_name)
                _set_if_has(model, "rating", r.rating)
                _set_if_has(model, "text", r.text)
                _set_if_has(model, "review_text", r.text)
                _set_if_has(model, "google_review_time", review_date)
                _set_if_has(model, "review_date", review_date)
                _set_if_has(model, "sentiment_score", None)
                _set_if_has(model, "sentiment", None)
                _set_if_has(model, "platform", r.source_platform or "Google")
                _set_if_has(model, "source_platform", r.source_platform or "Google")
                _set_if_has(model, "competitor_name", r.competitor_name)
                _set_if_has(model, "profile_photo_url", r.additional_fields.get("profile_photo_url") if r.additional_fields else None)

                db.add(model)
                total_saved += 1

        await db.commit()
        return {
            "status": "success",
            "reviews_fetched": total_fetched,
            "reviews_saved": total_saved,
            "date_range": {
                "start_date": start_dt.isoformat() if start_dt else None,
                "end_date": end_dt.isoformat() if end_dt else None,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to ingest reviews: {str(e)}")
