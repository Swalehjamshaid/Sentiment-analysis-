# filename: app/routes/reviews.py
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import and_, asc, cast, Date, desc, func, or_, select

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.google_reviews import (
    OutscraperReviewsService,
    ReviewData,
    CompanyReviews,
    ingest_company_reviews,
    ingest_multi_company_reviews,
    run_batch_review_ingestion,
)

router = APIRouter(tags=["reviews"])
logger = logging.getLogger("app.reviews")

DEFAULT_LIMIT = 200
MAX_LIMIT = 2000
DEFAULT_DAYS = 30

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _parse_date(s: Optional[str]) -> Optional[date]:
    """Parse string into date object; fallback to None on failure."""
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _range_or_default(start: Optional[str], end: Optional[str], default_days: int = DEFAULT_DAYS):
    """Return start and end dates; apply default if missing; ensure start <= end."""
    today = date.today()
    e = _parse_date(end) or today
    s = _parse_date(start) or (e - timedelta(days=default_days - 1))
    if s > e:
        s, e = e, s
    return s, e


def _date_col():
    """Return the Review date column for filtering; coalesce multiple date fields."""
    base = getattr(Review, "google_review_time", None)
    review_date = getattr(Review, "review_date", None)
    created = getattr(Review, "created_at", None)
    if base is not None and review_date is not None and created is not None:
        return cast(func.coalesce(Review.google_review_time, Review.review_date, Review.created_at), Date)
    if base is not None and review_date is not None:
        return cast(func.coalesce(Review.google_review_time, Review.review_date), Date)
    if base is not None and created is not None:
        return cast(func.coalesce(Review.google_review_time, Review.created_at), Date)
    return cast(Review.google_review_time, Date)


async def _get_reviews_client(request: Request) -> Optional[Any]:
    """Fetch a reviews client from app.state; placeholder for API keys/config."""
    app = request.app
    client = getattr(app.state, "reviews_client", None)
    if client and hasattr(client, "configure"):
        # Example: client.configure(api_key="YOUR_API_KEY_HERE")
        pass
    return client


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/reviews")
async def list_reviews(
    request: Request,
    company_id: int = Query(...),
    start: Optional[str] = None,
    end: Optional[str] = None,
    sort: str = Query("newest", regex="^(newest|oldest|highest|lowest)$"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
):
    """Fetch reviews for a company within a date range, with sorting and limit."""
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")

    s, e = _range_or_default(start, end)
    async with get_session() as session:
        dc = _date_col()
        order = desc(dc)
        if sort == "oldest":
            order = asc(dc)
        elif sort == "highest":
            order = desc(Review.rating)
        elif sort == "lowest":
            order = asc(Review.rating)

        rows = (await session.execute(
            select(
                Review.id,
                Review.author_name,
                Review.rating,
                Review.text,
                Review.google_review_time,
                Review.profile_photo_url,
                Review.sentiment_score,
            )
            .where(and_(Review.company_id == company_id, dc >= s, dc <= e))
            .order_by(order)
            .limit(limit)
        )).all()

    feed = []
    for r in rows:
        when = r.google_review_time
        ts_str = when.strftime("%Y-%m-%d") if isinstance(when, datetime) else (str(when) if when else "")
        feed.append({
            "id": r.id,
            "author_name": r.author_name or "Anonymous",
            "rating": float(r.rating or 0.0),
            "text": r.text or "",
            "review_time": ts_str,
            "profile_photo_url": r.profile_photo_url or "",
            "sentiment_score": float(r.sentiment_score or 0.0) if r.sentiment_score is not None else None,
        })

    return {
        "window": {"start": str(s), "end": str(e)},
        "company_id": company_id,
        "sort": sort,
        "limit": limit,
        "count": len(feed),
        "feed": feed,
    }


@router.get("/api/reviews/feed/{company_id}")
async def legacy_feed(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Legacy endpoint that calls the main list_reviews function."""
    return await list_reviews(request, company_id=company_id, start=start, end=end)


@router.post("/api/reviews/ingest/{company_id}")
async def ingest_reviews_endpoint(
    request: Request,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    max_reviews: Optional[int] = Query(None, ge=1, le=5000),
):
    """Fetch and ingest reviews for a single company; avoids duplicate ingestion."""
    client = await _get_reviews_client(request)
    if client is None:
        raise HTTPException(status_code=503, detail="Reviews client not configured")

    async with get_session() as session:
        company = await session.get(Company, company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

    s, e = _range_or_default(start, end)
    s_dt = datetime.combine(s, datetime.min.time())
    e_dt = datetime.combine(e, datetime.max.time())

    summary = await run_batch_review_ingestion(client, [company], start=s_dt, end=e_dt, max_reviews=max_reviews)
    return summary


@router.get("/api/reviews/competitors/{company_id}")
async def competitor_analytics(
    request: Request,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    names: Optional[str] = None,
):
    """Fetch competitor reviews analytics with counts and average ratings."""
    s, e = _range_or_default(start, end)

    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
        q = select(Company).where(Company.id != company_id)
        filters = []
        if names:
            for n in [x.strip() for x in names.split(',') if x.strip()]:
                try:
                    filters.append(Company.name.ilike(f"%{n}%"))
                except Exception:
                    filters.append(Company.name.like(f"%{n}%"))
        if filters:
            q = q.where(or_(*filters))
        companies = (await session.execute(q)).scalars().all() or []

    results = []
    async with get_session() as session:
        dc = _date_col()
        for c in companies:
            row = (await session.execute(
                select(func.count(Review.id).label("count"), func.avg(Review.rating).label("avg_rating"))
                .where(and_(Review.company_id == c.id, dc >= s, dc <= e))
            )).first()
            results.append({
                "company_id": int(c.id),
                "name": getattr(c, "name", ""),
                "count": int(row.count or 0) if row else 0,
                "avg_rating": round(float(row.avg_rating or 0.0), 3) if row else 0.0,
            })

    results.sort(key=lambda x: (-x["count"], x["name"]))
    return {"window": {"start": str(s), "end": str(e)}, "competitors": results}


@router.post("/api/reviews/ingest/batch")
async def batch_ingest_reviews(
    request: Request,
    company_ids: str = Query(..., description="Comma-separated company IDs"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    max_reviews: Optional[int] = Query(None, ge=1, le=5000),
):
    """Batch ingestion for multiple companies; duplicates handled internally."""
    client = await _get_reviews_client(request)
    if client is None:
        raise HTTPException(status_code=503, detail="Reviews client not configured")

    ids = []
    for x in company_ids.split(','):
        x = x.strip()
        if x:
            try:
                ids.append(int(x))
            except Exception:
                continue
    if not ids:
        raise HTTPException(status_code=400, detail="No valid company IDs provided")

    async with get_session() as session:
        rows = (await session.execute(select(Company).where(Company.id.in_(ids)))).scalars().all() or []
    if not rows:
        raise HTTPException(status_code=404, detail="No companies found")

    s, e = _range_or_default(start, end)
    s_dt = datetime.combine(s, datetime.min.time())
    e_dt = datetime.combine(e, datetime.max.time())

    summary = await run_batch_review_ingestion(client, rows, start=s_dt, end=e_dt, max_reviews=max_reviews)
    return summary
