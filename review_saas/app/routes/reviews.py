# filename: app/routes/reviews.py
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

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
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _range_or_default(start: Optional[str], end: Optional[str], default_days: int = DEFAULT_DAYS) -> tuple[date, date]:
    today = date.today()
    e = _parse_date(end) or today
    s = _parse_date(start) or (e - timedelta(days=default_days - 1))
    if s > e:
        s, e = e, s
    return s, e


def _date_col():
    """
    Picks the best available column to represent the review's date for filtering/sorting.
    Prefers google_review_time, then review_date, then created_at, cast to Date.
    """
    base = getattr(Review, "google_review_time", None)
    review_date = getattr(Review, "review_date", None)
    created = getattr(Review, "created_at", None)

    cols = [c for c in (base, review_date, created) if c is not None]
    if not cols:
        # Fallback: cast a known column to keep SQL valid; use created_at if absolutely nothing else
        return cast(Review.created_at, Date)  # type: ignore
    if len(cols) > 1:
        return cast(func.coalesce(*cols), Date)
    return cast(cols[0], Date)


async def _get_reviews_client(request: Request) -> Optional[Any]:
    """
    Returns a preconfigured Outscraper/Reviews client attached to app.state.reviews_client.
    If not present, returns None (caller decides error handling).
    """
    app = request.app
    client = getattr(app.state, "reviews_client", None)
    return client


def _safe_iso(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    try:
        return dt.isoformat()
    except Exception:
        try:
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            return str(dt)


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
    logger.info("GET /api/reviews company_id=%s start=%s end=%s sort=%s limit=%s", company_id, start, end, sort, limit)

    # Validate company existence early
    async with get_session() as session:
        if not await session.get(Company, company_id):
            logger.warning("GET /api/reviews company_id=%s -> 404 (company not found)", company_id)
            raise HTTPException(status_code=404, detail="Company not found")

    s, e = _range_or_default(start, end)
    logger.debug("GET /api/reviews window resolved start=%s end=%s", s, e)

    async with get_session() as session:
        dc = _date_col()

        order_map = {
            "newest": desc(dc),
            "oldest": asc(dc),
            "highest": desc(Review.rating),
            "lowest": asc(Review.rating),
        }

        stmt = (
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
            .order_by(order_map.get(sort, desc(dc)))
            .limit(limit)
        )

        rows = (await session.execute(stmt)).all()

    feed = []
    for r in rows:
        when = r.google_review_time
        # Preserve existing string shape (YYYY-MM-DD if date-like, otherwise ISO)
        if isinstance(when, datetime):
            ts = when.strftime("%Y-%m-%d")
        else:
            ts = str(when) if when is not None else ""
        feed.append(
            {
                "id": r.id,
                "author_name": r.author_name or "Anonymous",
                "rating": float(r.rating or 0.0),
                "text": r.text or "",
                "review_time": ts,
                "profile_photo_url": r.profile_photo_url or "",
                "sentiment_score": float(r.sentiment_score or 0.0)
                if r.sentiment_score is not None
                else None,
            }
        )

    resp = {
        "window": {"start": str(s), "end": str(e)},
        "company_id": company_id,
        "sort": sort,
        "limit": limit,
        "count": len(feed),
        "feed": feed,
    }
    logger.info("GET /api/reviews company_id=%s -> %s items", company_id, resp["count"])
    return resp


@router.get("/api/reviews/feed/{company_id}")
async def legacy_feed(
    request: Request,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    """Legacy endpoint calling main list_reviews."""
    logger.info("GET /api/reviews/feed/%s start=%s end=%s", company_id, start, end)
    return await list_reviews(request, company_id=company_id, start=start, end=end)


@router.post("/api/reviews/ingest/{company_id}")
async def ingest_reviews_endpoint(
    request: Request,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    max_reviews: Optional[int] = Query(None, ge=1, le=5000),
):
    """Fetch and ingest reviews for a single company."""
    logger.info("POST /api/reviews/ingest/%s start=%s end=%s max_reviews=%s", company_id, start, end, max_reviews)
    client = await _get_reviews_client(request)
    if client is None:
        logger.error("POST /api/reviews/ingest/%s -> 503 (reviews client not configured)", company_id)
        raise HTTPException(status_code=503, detail="Reviews client not configured")

    # Ensure company exists and load it
    async with get_session() as session:
        company = await session.get(Company, company_id)
        if not company:
            logger.warning("POST /api/reviews/ingest/%s -> 404 (company not found)", company_id)
            raise HTTPException(status_code=404, detail="Company not found")

    # Determine range:
    # - If no dates provided -> default window (DEFAULT_DAYS)
    # - If dates provided -> exact window (inclusive)
    s, e = _range_or_default(start, end, default_days=15) if not (start or end) else _range_or_default(start, end)
    s_dt = datetime.combine(s, datetime.min.time())
    e_dt = datetime.combine(e, datetime.max.time())
    logger.debug("POST /api/reviews/ingest/%s window start=%s end=%s", company_id, s_dt, e_dt)

    # Delegate to service orchestration (signature preserved)
    result = await run_batch_review_ingestion(
        client, [company], start=s_dt, end=e_dt, max_reviews=max_reviews
    )
    logger.info("POST /api/reviews/ingest/%s -> summary=%s", company_id, result)
    return result


@router.get("/api/reviews/competitors/{company_id}")
async def competitor_analytics(
    request: Request,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    names: Optional[str] = None,
):
    """Fetch competitor reviews analytics with counts and average ratings."""
    logger.info(
        "GET /api/reviews/competitors/%s start=%s end=%s names=%s",
        company_id,
        start,
        end,
        names,
    )
    s, e = _range_or_default(start, end)

    # Validate base company
    async with get_session() as session:
        if not await session.get(Company, company_id):
            logger.warning("GET /api/reviews/competitors/%s -> 404 (company not found)", company_id)
            raise HTTPException(status_code=404, detail="Company not found")

        q = select(Company).where(Company.id != company_id)

        if names:
            filters = [
                Company.name.ilike(f"%{n.strip()}%")
                for n in names.split(",")
                if n.strip()
            ]
            if filters:
                q = q.where(or_(*filters))

        companies = (await session.execute(q)).scalars().all() or []

    results = []

    # Aggregate counts and average ratings per competitor
    async with get_session() as session:
        dc = _date_col()

        for c in companies:
            row = (
                await session.execute(
                    select(
                        func.count(Review.id).label("count"),
                        func.avg(Review.rating).label("avg_rating"),
                    ).where(and_(Review.company_id == c.id, dc >= s, dc <= e))
                )
            ).first()

            results.append(
                {
                    "company_id": int(c.id),
                    "name": getattr(c, "name", ""),
                    "count": int(row.count or 0) if row else 0,  # type: ignore[attr-defined]
                    "avg_rating": round(float(row.avg_rating or 0.0), 3) if row else 0.0,  # type: ignore[attr-defined]
                }
            )

    # Sort by count desc, then name
    results.sort(key=lambda x: (-x["count"], x["name"]))

    resp = {"window": {"start": str(s), "end": str(e)}, "competitors": results}
    logger.info(
        "GET /api/reviews/competitors/%s -> %s competitors",
        company_id,
        len(results),
    )
    return resp


@router.post("/api/reviews/ingest/batch")
async def batch_ingest_reviews(
    request: Request,
    company_ids: str = Query(..., description="Comma-separated company IDs"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    max_reviews: Optional[int] = Query(None, ge=1, le=5000),
):
    """Batch ingestion for multiple companies."""
    logger.info(
        "POST /api/reviews/ingest/batch company_ids=%s start=%s end=%s max_reviews=%s",
        company_ids,
        start,
        end,
        max_reviews,
    )
    client = await _get_reviews_client(request)
    if client is None:
        logger.error("POST /api/reviews/ingest/batch -> 503 (reviews client not configured)")
        raise HTTPException(status_code=503, detail="Reviews client not configured")

    # Parse IDs
    ids: list[int] = []
    for x in company_ids.split(","):
        x = x.strip()
        if not x:
            continue
        try:
            ids.append(int(x))
        except Exception:
            continue

    if not ids:
        logger.warning("POST /api/reviews/ingest/batch -> 400 (no valid company IDs)")
        raise HTTPException(status_code=400, detail="No valid company IDs provided")

    # Load companies
    async with get_session() as session:
        rows = (await session.execute(select(Company).where(Company.id.in_(ids)))).scalars().all() or []

    if not rows:
        logger.warning("POST /api/reviews/ingest/batch -> 404 (no companies found)")
        raise HTTPException(status_code=404, detail="No companies found")

    # Determine range:
    # - If no dates provided -> default window (DEFAULT_DAYS) for batch
    # - If dates provided -> exact window (inclusive)
    s, e = _range_or_default(start, end, default_days=15) if not (start or end) else _range_or_default(start, end)
    s_dt = datetime.combine(s, datetime.min.time())
    e_dt = datetime.combine(e, datetime.max.time())
    logger.debug("POST /api/reviews/ingest/batch window start=%s end=%s count=%s", s_dt, e_dt, len(rows))

    # Delegate to service orchestration (signature preserved)
    result = await run_batch_review_ingestion(
        client, rows, start=s_dt, end=e_dt, max_reviews=max_reviews
    )
    logger.info("POST /api/reviews/ingest/batch -> summary=%s", result)
    return result
