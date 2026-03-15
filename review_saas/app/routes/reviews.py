# filename: app/routes/reviews.py
from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import date, datetime, timedelta
from contextlib import asynccontextmanager

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, cast, Date, desc, select, func, Integer, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.google_reviews import run_batch_review_ingestion

router = APIRouter(tags=["reviews"])
logger = logging.getLogger("app.reviews")

# ---------------------------------------------------------
# Configuration & Utilities
# ---------------------------------------------------------
# NOTE: For security, avoid hardcoding API keys. Ensure one of these env vars is set.
GOOGLE_API_KEY = (
    os.getenv("GOOGLE_PLACES_API_KEY")
    or os.getenv("GOOGLE_MAPS_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
)

HTTPX_TIMEOUT = 30.0


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None


def _resolve_range(start: Optional[str], end: Optional[str]) -> Tuple[date, date]:
    today = date.today()
    e_dt = _parse_date(end) or today
    s_dt = _parse_date(start) or (e_dt - timedelta(days=14))
    return s_dt, e_dt


def _safe_day_str(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    try:
        return dt.date().isoformat()
    except Exception:
        return ""


@asynccontextmanager
async def _httpx_client():
    async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
        yield client


# ---------------------------------------------------------
# GOOGLE PROXY ENDPOINTS (Frontend -> reviews.py -> Google)
# ---------------------------------------------------------
@router.get("/api/google_autocomplete")
async def google_autocomplete(input: str) -> Dict[str, Any]:
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Google API key missing")

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {"input": input, "key": GOOGLE_API_KEY}

    try:
        async with _httpx_client() as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return {"predictions": r.json().get("predictions", [])}
    except Exception as e:
        logger.error(f"Autocomplete Error: {str(e)}")
        raise HTTPException(status_code=502, detail="Upstream Google API failure")


@router.get("/api/google/place/details")
async def google_place_details(place_id: str) -> Dict[str, Any]:
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Google API key missing")

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,rating,place_id",
        "key": GOOGLE_API_KEY,
    }

    try:
        async with _httpx_client() as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            res = r.json().get("result", {}) or {}
            return {
                "name": res.get("name"),
                "address": res.get("formatted_address"),
                "rating": res.get("rating"),
                "place_id": res.get("place_id"),
            }
    except Exception as e:
        logger.error(f"Details Error: {str(e)}")
        raise HTTPException(status_code=502, detail="Upstream Google API failure")


# ---------------------------------------------------------
# Helper: Analytics builders (DB -> Aggregations -> JSON)
# ---------------------------------------------------------
async def _build_analytics(
    session: AsyncSession,
    company_id: int,
    s_date: date,
    e_date: date,
) -> Dict[str, Any]:
    """Compute analytics for a company within a date range.

    Returns keys:
      - totals: {total_reviews, avg_rating, earliest_review, latest_review}
      - ratings: {1..5}
      - sentiments: {negative, neutral, positive}
      - timeseries: [{date, count, avg_rating}]
    """
    # Common filter
    base_filter = and_(
        Review.company_id == company_id,
        cast(Review.google_review_time, Date) >= s_date,
        cast(Review.google_review_time, Date) <= e_date,
    )

    # Totals and averages
    totals_stmt = select(
        func.count(Review.id),
        func.avg(Review.rating),
        func.min(Review.google_review_time),
        func.max(Review.google_review_time),
    ).where(base_filter)

    # Ratings histogram (cast rating to integer buckets 1..5)
    ratings_stmt = (
        select(cast(Review.rating, Integer).label("bucket"), func.count().label("n"))
        .where(base_filter)
        .group_by("bucket")
    )

    # Sentiment buckets (thresholds: neg < -0.2, neu [-0.2, 0.2], pos > 0.2)
    sentiments_stmt = select(
        func.sum(case((Review.sentiment_score < -0.2, 1), else_=0)).label("negative"),
        func.sum(
            case(
                (and_(Review.sentiment_score >= -0.2, Review.sentiment_score <= 0.2), 1),
                else_=0,
            )
        ).label("neutral"),
        func.sum(case((Review.sentiment_score > 0.2, 1), else_=0)).label("positive"),
    ).where(base_filter)

    # Daily timeseries (count and avg rating per day)
    day_col = cast(Review.google_review_time, Date).label("day")
    timeseries_stmt = (
        select(day_col, func.count().label("count"), func.avg(Review.rating).label("avg_rating"))
        .where(base_filter)
        .group_by(day_col)
        .order_by(day_col)
    )

    # Execute queries
    totals_res = await session.execute(totals_stmt)
    ratings_res = await session.execute(ratings_stmt)
    sentiments_res = await session.execute(sentiments_stmt)
    timeseries_res = await session.execute(timeseries_stmt)

    total_count, avg_rating, earliest_dt, latest_dt = totals_res.one_or_none() or (0, None, None, None)

    # Build ratings histogram 1..5 with zeros
    ratings_hist = {i: 0 for i in range(1, 6)}
    for bucket, n in ratings_res.all():
        if bucket in ratings_hist:
            ratings_hist[bucket] = int(n)

    sentiments_row = sentiments_res.one_or_none()
    sentiments = {
        "negative": int(sentiments_row[0]) if sentiments_row and sentiments_row[0] is not None else 0,
        "neutral": int(sentiments_row[1]) if sentiments_row and sentiments_row[1] is not None else 0,
        "positive": int(sentiments_row[2]) if sentiments_row and sentiments_row[2] is not None else 0,
    }

    timeseries = [
        {
            "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
            "count": int(c or 0),
            "avg_rating": float(ar) if ar is not None else None,
        }
        for d, c, ar in timeseries_res.all()
    ]

    totals = {
        "total_reviews": int(total_count or 0),
        "avg_rating": float(avg_rating) if avg_rating is not None else None,
        "earliest_review": earliest_dt.date().isoformat() if earliest_dt else None,
        "latest_review": latest_dt.date().isoformat() if latest_dt else None,
    }

    return {
        "totals": totals,
        "ratings": ratings_hist,
        "sentiments": sentiments,
        "timeseries": timeseries,
    }


async def _build_comparisons(
    session: AsyncSession,
    company_ids: List[int],
    s_date: date,
    e_date: date,
) -> List[Dict[str, Any]]:
    """Build per-company comparison summaries for the given IDs."""
    if not company_ids:
        return []

    # Fetch company names in one go
    companies_res = await session.execute(select(Company).where(Company.id.in_(company_ids)))
    companies = {c.id: c for c in companies_res.scalars().all()}

    comparisons: List[Dict[str, Any]] = []
    for cid in company_ids:
        analytics = await _build_analytics(session, cid, s_date, e_date)
        c = companies.get(cid)
        comparisons.append(
            {
                "company_id": cid,
                "company_name": c.name if c else f"Company {cid}",
                "totals": analytics.get("totals", {}),
                "avg_rating": analytics.get("totals", {}).get("avg_rating"),
            }
        )
    return comparisons


# ---------------------------------------------------------
# INGESTION API (Service -> Database)
# ---------------------------------------------------------
@router.post("/api/reviews/ingest/{company_id}")
async def trigger_ingestion(
    request: Request,
    company_id: int,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    max_reviews: Optional[int] = Query(None, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
):
    """Trigger review ingestion for a company within a date window.

    Aligns with flow: Dashboard -> reviews.py -> google_reviews.py (service) -> models -> DB.
    """
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    client = getattr(request.app.state, "reviews_client", None)
    if not client:
        raise HTTPException(status_code=503, detail="Ingestion client not initialized")

    s_date, e_date = _resolve_range(start, end)
    logger.info(
        f"🔄 INGESTION TRIGGERED: {company.name} | Window: {s_date} to {e_date} | max_reviews={max_reviews}"
    )

    try:
        summary = await run_batch_review_ingestion(
            client=client,
            entities=[company],
            start=datetime.combine(s_date, datetime.min.time()),
            end=datetime.combine(e_date, datetime.max.time()),
            session=session,
            max_reviews=max_reviews,  # service accepts max_reviews per flow design
        )

        return {
            "status": "success",
            "company": company.name,
            "sync_range": {"start": s_date.isoformat(), "end": e_date.isoformat()},
            "ingestion_summary": summary,
        }

    except Exception as e:
        logger.exception(f"Ingestion failed for {company.name}: {e}")
        raise HTTPException(status_code=500, detail="Review ingestion process failed")


# ---------------------------------------------------------
# DASHBOARD DATA API (DB -> Structured JSON for Frontend)
# ---------------------------------------------------------
@router.get("/api/reviews")
async def get_reviews(
    company_id: int = Query(...),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=2000),
    include_analytics: bool = Query(True),
    competitor_ids: Optional[List[int]] = Query(None, description="Optional competitor company_ids for comparisons"),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Return feed + (optionally) analytics and competitor comparisons.

    Aligns with flow: DB -> API Response (JSON) -> Dashboard UI.
    """
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    s_date, e_date = _resolve_range(start, end)

    # Base query for feed
    stmt = (
        select(Review)
        .where(
            and_(
                Review.company_id == company_id,
                cast(Review.google_review_time, Date) >= s_date,
                cast(Review.google_review_time, Date) <= e_date,
            )
        )
        .order_by(desc(Review.google_review_time))
        .limit(limit)
    )

    try:
        result = await session.execute(stmt)
        rows = result.scalars().all()

        feed: List[Dict[str, Any]] = []
        for row in rows:
            feed.append(
                {
                    "author_name": str(row.author_name or "Anonymous"),
                    "rating": float(row.rating or 0.0),
                    "sentiment_score": float(row.sentiment_score or 0.0),
                    "review_time": _safe_day_str(row.google_review_time),
                    "text": str(row.text or ""),
                }
            )

        payload: Dict[str, Any] = {"feed": feed, "count": len(feed)}

        # Optional analytics
        if include_analytics:
            analytics = await _build_analytics(session, company_id, s_date, e_date)
            payload["analytics"] = analytics

        # Optional competitor comparisons
        if competitor_ids:
            # Ensure baseline is included for side-by-side view
            unique_ids = []
            seen = set()
            for cid in [company_id] + competitor_ids:
                if cid not in seen:
                    seen.add(cid)
                    unique_ids.append(cid)

            comparisons = await _build_comparisons(session, unique_ids, s_date, e_date)
            payload["comparisons"] = comparisons

        logger.info(
            f"📊 DASHBOARD DATA: feed={len(feed)} | analytics={'yes' if include_analytics else 'no'} | comparisons={len(payload.get('comparisons', [])) if 'comparisons' in payload else 0} | company={company.name}"
        )
        return payload

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database Query Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard reviews")
