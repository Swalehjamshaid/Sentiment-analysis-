# filename: app/routes/reviews.py
from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional
from datetime import date, datetime
from contextlib import asynccontextmanager

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, asc, cast, Date, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.models import Company, Review  # type: ignore

router = APIRouter(tags=["reviews"])
logger = logging.getLogger("app.reviews")

# ---------------------------------------------------------
# Google API key config (environment)
# ---------------------------------------------------------
GOOGLE_API_KEY = (
    os.getenv("GOOGLE_PLACES_API_KEY")
    or os.getenv("GOOGLE_MAPS_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
)

HTTPX_TIMEOUT = 15.0  # seconds


# ---------------------------------------------------------
# Utilities
# ---------------------------------------------------------
def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    try:
        # ISO fallback
        return datetime.fromisoformat(s).date()
    except Exception:
        return None


def _safe_day_str(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    try:
        return dt.date().isoformat()
    except Exception:
        return ""


def _sentiment_from_rating(rating: Optional[float]) -> float:
    # Map 1..5 to [-1..+1] centered around 3 -> 0
    if rating is None:
        return 0.0
    try:
        r = max(1.0, min(5.0, float(rating)))
        return (r - 3.0) / 2.0
    except Exception:
        return 0.0


@asynccontextmanager
async def _httpx_client():
    async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
        yield client


# ---------------------------------------------------------
# GOOGLE AUTOCOMPLETE PROXY
# ---------------------------------------------------------
@router.get("/api/google_autocomplete")
async def google_autocomplete(input: str) -> Dict[str, Any]:
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Google API key missing")

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": input,
        "key": GOOGLE_API_KEY,
        # You can add more params here if needed (language, locationbias, etc.)
    }

    try:
        async with _httpx_client() as client:
            r = await client.get(url, params=params)
        data = r.json()
        # Return only the predictions list to match the expected frontend structure
        return {"predictions": data.get("predictions", [])}
    except httpx.HTTPError as he:
        logger.exception("Google Autocomplete HTTP error: %s", he)
        raise HTTPException(status_code=502, detail="Google Autocomplete upstream error")
    except Exception as ex:
        logger.exception("Google Autocomplete unknown error: %s", ex)
        raise HTTPException(status_code=500, detail="Google Autocomplete failed")


# ---------------------------------------------------------
# GOOGLE PLACE DETAILS PROXY
# ---------------------------------------------------------
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
        data = r.json()
        result = data.get("result", {}) or {}
        return {
            "name": result.get("name"),
            "address": result.get("formatted_address"),
            "rating": result.get("rating"),
            "place_id": result.get("place_id"),
        }
    except httpx.HTTPError as he:
        logger.exception("Google Place Details HTTP error: %s", he)
        raise HTTPException(status_code=502, detail="Google Place Details upstream error")
    except Exception as ex:
        logger.exception("Google Place Details unknown error: %s", ex)
        raise HTTPException(status_code=500, detail="Google Place Details failed")


# ---------------------------------------------------------
# MAIN REVIEWS API (reads from PostgreSQL)
# ---------------------------------------------------------
@router.get("/api/reviews")
async def get_reviews(
    company_id: int = Query(..., description="Company ID"),
    start: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(50, ge=1, le=2000, description="Max number of reviews"),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    Returns processed review feed for the dashboard.
    Pulls reviews from PostgreSQL (already ingested/normalized).
    Response structure:
      {
        "feed": [
           { "author_name", "rating", "sentiment_score", "review_time", "text" }, ...
        ]
      }
    """
    # Validate company
    c_obj = await session.get(Company, company_id)
    if not c_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    # Parse window
    start_d = _parse_date(start)
    end_d = _parse_date(end)

    # Build date column preference and filters
    # Prefer google_review_time; fallback to created_at if necessary
    date_col = getattr(Review, "google_review_time", None) or getattr(Review, "created_at", None)
    if date_col is None:
        raise HTTPException(status_code=500, detail="Review date column not available")

    filters = [Review.company_id == company_id]  # type: ignore[attr-defined]
    if start_d is not None:
        filters.append(cast(date_col, Date) >= start_d)
    if end_d is not None:
        filters.append(cast(date_col, Date) <= end_d)

    stmt = (
        select(
            Review.author_name,
            Review.rating,
            Review.text,
            Review.google_review_time,
            Review.sentiment_score,
        )
        .where(and_(*filters))
        .order_by(desc(date_col))
        .limit(limit)
    )

    result = await session.execute(stmt)
    rows = result.all()

    feed: List[Dict[str, Any]] = []
    for row in rows:
        author_name = row.author_name
        rating = float(row.rating or 0.0) if row.rating is not None else 0.0
        sentiment = row.sentiment_score
        if sentiment is None:
            sentiment = _sentiment_from_rating(rating)
        review_time = _safe_day_str(row.google_review_time)
        feed.append(
            {
                "author_name": author_name,
                "rating": rating,
                "sentiment_score": float(sentiment),
                "review_time": review_time,
                "text": row.text or "",
            }
        )

    return {"feed": feed}
