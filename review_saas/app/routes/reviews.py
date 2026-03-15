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
# GOOGLE PROXY ENDPOINTS
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
# INGESTION API
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
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    client = getattr(request.app.state, "reviews_client", None)
    if not client:
        raise HTTPException(status_code=503, detail="Ingestion client not initialized")

    s_date, e_date = _resolve_range(start, end)

    logger.info(
        f"🔄 INGESTION TRIGGERED: {company.name} | Window: {s_date} to {e_date}"
    )

    try:
        summary = await run_batch_review_ingestion(
            client=client,
            entities=[company],
            start=datetime.combine(s_date, datetime.min.time()),
            end=datetime.combine(e_date, datetime.max.time()),
            session=session,
            max_reviews=max_reviews,
        )

        return {
            "status": "success",
            "company": company.name,
            "ingestion_summary": summary,
        }

    except Exception as e:
        logger.exception(f"Ingestion failed for {company.name}: {e}")
        raise HTTPException(status_code=500, detail="Review ingestion process failed")


# ---------------------------------------------------------
# DASHBOARD DATA API
# ---------------------------------------------------------
@router.get("/api/reviews")
async def get_reviews(
    request: Request,
    company_id: int = Query(...),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=2000),
    include_analytics: bool = Query(True),
    competitor_ids: Optional[List[int]] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:

    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    s_date, e_date = _resolve_range(start, end)

    # ---------------------------------------------------------
    # AUTO INGESTION IF DATABASE EMPTY
    # ---------------------------------------------------------
    client = getattr(request.app.state, "reviews_client", None)

    count_stmt = select(func.count(Review.id)).where(
        Review.company_id == company_id
    )

    count_res = await session.execute(count_stmt)
    existing_reviews = count_res.scalar() or 0

    if existing_reviews == 0 and client:
        logger.info(f"⚡ No reviews found for {company.name}. Starting ingestion...")

        await run_batch_review_ingestion(
            client=client,
            entities=[company],
            start=datetime.combine(s_date, datetime.min.time()),
            end=datetime.combine(e_date, datetime.max.time()),
            session=session,
            max_reviews=200,
        )

    # ---------------------------------------------------------
    # FETCH REVIEWS
    # ---------------------------------------------------------
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

        logger.info(
            f"📊 DASHBOARD DATA: feed={len(feed)} | company={company.name}"
        )

        return payload

    except Exception as e:
        logger.error(f"Database Query Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard reviews")
