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
    If only date is provided, expands start->00:00:00 and end->23:59:59.999999.
    """
    def _parse(s: Optional[str]) -> Optional[datetime]:
        if not s:
            return None
        try:
            # Simple date
            if len(s) == 10:
                return datetime.strptime(s, "%Y-%m-%d")
            # ISO (strip Z to allow +00:00)
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    s = _parse(start_date)
    e = _parse(end_date)

    # If user provided one side only, fill the other
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

# ---------------------------------------------------------
# Ingest Reviews Based on Date Range (defaults to last 30d)
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
    """
    Fetch reviews via Outscraper/Google and store them.
    - If start_date/end_date omitted, defaults to last 30 days inclusive.
    - Supports competitor place_ids; all rows are stored under the same company_id
      but retain `competitor_name` where available.
    - Uses flexible field mapping and skips duplicates by `external_review_id` if your model has it.
    """
    try:
        # Validate company
        result = await db.execute(select(Company).filter(Company.id == company_id))
        company = result.scalars().first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        start_dt, end_dt = _normalize_window(start_date, end_date)

        # Build entities list (primary + competitors)
        entities: List[str] = [place_id]
        if competitor_place_ids:
            entities.extend([pid for pid in competitor_place_ids if pid])

        # Build the service with your real reviews client
        client = _reviews_client(request)
        service = OutscraperReviewsService(client)

        total_saved = 0
        total_fetched = 0

        for pid in entities:
            # Fetch with inclusive date range; service filters strictly within [start_dt, end_dt]
            reviews_data: List[ReviewData] = service.fetch_reviews(
                place_id=pid,
                start_date=start_dt,
                end_date=end_dt,
                max_reviews=limit,
            )
            total_fetched += len(reviews_data)

            for r in reviews_data:
                review_date = r.time_created

                # Duplicate guard by external ID if available; fallback to composite
                external_id_field = "external_review_id" if hasattr(Review, "external_review_id") else None

                if external_id_field:
                    exist = await db.execute(
                        select(Review).filter(getattr(Review, external_id_field) == r.review_id)
                    )
                    if exist.scalars().first():
                        continue
                else:
                    # Fallback composite duplicate check
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
                _set_if_has(model, "external_review_id", r.review_id)  # if exists in your model
                _set_if_has(model, "google_review_id", r.review_id)    # alt field if you have it
                _set_if_has(model, "author_name", r.author_name)
                _set_if_has(model, "author", r.author_name)  # compatibility
                _set_if_has(model, "rating", r.rating)
                _set_if_has(model, "text", r.text)
                _set_if_has(model, "review_text", r.text)    # compatibility
                _set_if_has(model, "google_review_time", review_date)
                _set_if_has(model, "review_date", review_date)
                _set_if_has(model, "sentiment_score", None)  # leave for later processing
                _set_if_has(model, "sentiment", None)
                _set_if_has(model, "platform", r.source_platform or "Google")
                _set_if_has(model, "source_platform", r.source_platform or "Google")
                _set_if_has(model, "competitor_name", r.competitor_name)
                _set_if_has(model, "profile_photo_url", r.additional_fields.get("profile_photo_url"))

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

# ---------------------------------------------------------
# Review Feed for Dashboard (defaults to last 30d)
# ---------------------------------------------------------
@router.get("/feed/{company_id}")
async def get_reviews_feed(
    company_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_session),
):
    """
    Returns filtered reviews for the dashboard.
    - Defaults to last 30 days when dates are not provided.
    - Returns dual-naming variants for compatibility.
    """
    s, e = _normalize_window(start_date, end_date)

    query = select(Review).filter(Review.company_id == company_id)

    # Apply date filter on preferred datetime column(s)
    if hasattr(Review, "google_review_time"):
        if s:
            query = query.filter(Review.google_review_time >= s)
        if e:
            query = query.filter(Review.google_review_time <= e)
    elif hasattr(Review, "review_date"):
        if s:
            query = query.filter(Review.review_date >= s)
        if e:
            query = query.filter(Review.review_date <= e)

    order_col = getattr(Review, "google_review_time", getattr(Review, "review_date", Review.id))
    query = query.order_by(order_col.desc()).limit(limit)

    result = await db.execute(query)
    reviews = result.scalars().all()

    def _s(dt):
        if not dt:
            return None
        try:
            return dt.isoformat()
        except Exception:
            return str(dt)

    out = []
    for r in reviews:
        author_name = getattr(r, "author_name", None) or getattr(r, "author", None)
        text = getattr(r, "text", None) or getattr(r, "review_text", None)
        dt = getattr(r, "google_review_time", None) or getattr(r, "review_date", None)
        sentiment = getattr(r, "sentiment_score", None)
        if sentiment is None:
            sentiment = getattr(r, "sentiment", None)
        out.append({
            "id": getattr(r, "id", None),
            "author_name": author_name,
            "author": author_name,  # duplicate for compatibility
            "rating": getattr(r, "rating", None),
            "text": text,
            "review_text": text,    # duplicate for compatibility
            "review_time": _s(dt),
            "date": _s(dt),
            "sentiment": sentiment,
            "competitor": getattr(r, "competitor_name", None),
            "competitor_name": getattr(r, "competitor_name", None),
            "platform": getattr(r, "source_platform", getattr(r, "platform", "Google")),
            "profile_photo_url": getattr(r, "profile_photo_url", None),
        })

    return {"status": "success", "reviews": out, "window": {"start": _s(s), "end": _s(e)}}

# ---------------------------------------------------------
# Competitor Analytics API (defaults to last 30d)
# ---------------------------------------------------------
@router.get("/competitors/{company_id}")
async def competitor_stats(
    company_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
):
    """
    Returns competitor review counts and ratings for the date window.
    Defaults to last 30 days if not provided.
    """
    s, e = _normalize_window(start_date, end_date)

    query = select(Review).filter(
        Review.company_id == company_id,
        Review.competitor_name != None,  # noqa: E711
    )

    if hasattr(Review, "google_review_time"):
        if s:
            query = query.filter(Review.google_review_time >= s)
        if e:
            query = query.filter(Review.google_review_time <= e)
    elif hasattr(Review, "review_date"):
        if s:
            query = query.filter(Review.review_date >= s)
        if e:
            query = query.filter(Review.review_date <= e)

    result = await db.execute(query)
    rows = result.scalars().all()

    competitor_counts = Counter(
        getattr(r, "competitor_name", None) for r in rows if getattr(r, "competitor_name", None)
    )

    competitor_ratings: Dict[str, List[float]] = {}
    for r in rows:
        name = getattr(r, "competitor_name", None)
        rating = getattr(r, "rating", None)
        if name and rating is not None:
            competitor_ratings.setdefault(name, []).append(float(rating))

    competitor_avg = {
        name: round(sum(vals) / len(vals), 2) if vals else 0.0
        for name, vals in competitor_ratings.items()
    }

    return {
        "window": {"start": s.isoformat() if s else None, "end": e.isoformat() if e else None},
        "competitor_review_count": dict(competitor_counts),
        "competitor_avg_rating": competitor_avg,
    }
