# filename: app/routes/dashboard.py
from __future__ import annotations

import logging
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, desc, asc, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.templating import Jinja2Templates

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.dashboard")


# =====================================================
# Utility: Safe Date Parser
# =====================================================
def parse_date(date_str: str | None):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: {date_str}. Use YYYY-MM-DD",
        )


# =====================================================
# UI Route
# =====================================================
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request}
    )


# =====================================================
# API: Company List
# =====================================================
@router.get("/api/companies/list")
async def api_companies_list():
    async with get_session() as session:
        stmt = select(Company.id, Company.name).order_by(Company.name)
        result = await session.execute(stmt)
        companies = result.all()

        return {
            "companies": [
                {"id": c.id, "name": c.name}
                for c in companies
            ]
        }


# =====================================================
# API: KPI Cards
# =====================================================
@router.get("/api/kpis")
async def api_kpis(company_id: int, start: str | None = None, end: str | None = None):
    start_date = parse_date(start)
    end_date = parse_date(end)

    async with get_session() as session:
        stmt = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent")
        ).where(Review.company_id == company_id)

        if start_date:
            stmt = stmt.where(cast(Review.review_time, Date) >= start_date)
        if end_date:
            stmt = stmt.where(cast(Review.review_time, Date) <= end_date)

        res = await session.execute(stmt)
        stats = res.first()

        return {
            "total_reviews": int(stats.total or 0),
            "avg_rating": round(float(stats.avg_rating or 0.0), 2),
            "avg_sentiment": round(float(stats.avg_sent or 0.0), 3),
        }


# =====================================================
# API: Review List
# =====================================================
@router.get("/api/reviews/list")
async def api_reviews_list(
    company_id: int,
    sort: str = "newest",
    start: str | None = None,
    end: str | None = None,
):
    start_date = parse_date(start)
    end_date = parse_date(end)

    async with get_session() as session:
        stmt = select(Review).where(
            Review.company_id == company_id
        )

        # Sorting
        if sort == "newest":
            stmt = stmt.order_by(desc(Review.review_time))
        elif sort == "oldest":
            stmt = stmt.order_by(asc(Review.review_time))
        elif sort == "highest":
            stmt = stmt.order_by(desc(Review.rating))
        elif sort == "lowest":
            stmt = stmt.order_by(asc(Review.rating))

        # Date filtering
        if start_date:
            stmt = stmt.where(cast(Review.review_time, Date) >= start_date)
        if end_date:
            stmt = stmt.where(cast(Review.review_time, Date) <= end_date)

        res = await session.execute(stmt.limit(50))
        items = res.scalars().all()

        return {
            "items": [
                {
                    "author_name": r.author_name or "Anonymous",
                    "rating": r.rating,
                    "text": r.text,
                    "review_time": r.review_time.strftime("%Y-%m-%d %H:%M")
                    if r.review_time
                    else "",
                }
                for r in items
            ]
        }


# =====================================================
# API: Reviews Time Series
# =====================================================
@router.get("/api/series/reviews")
async def api_series_reviews(
    company_id: int,
    start: str | None = None,
    end: str | None = None,
):
    start_date = parse_date(start)
    end_date = parse_date(end)

    async with get_session() as session:
        date_col = cast(Review.review_time, Date)

        stmt = select(
            date_col.label("date"),
            func.count(Review.id).label("value")
        ).where(Review.company_id == company_id)

        if start_date:
            stmt = stmt.where(date_col >= start_date)
        if end_date:
            stmt = stmt.where(date_col <= end_date)

        stmt = stmt.group_by(date_col).order_by(date_col)

        res = await session.execute(stmt)

        return {
            "series": [
                {"date": str(r.date), "value": int(r.value or 0)}
                for r in res.all()
            ]
        }


# =====================================================
# API: Ratings Distribution
# =====================================================
@router.get("/api/ratings/distribution")
async def api_ratings_distribution(company_id: int):
    async with get_session() as session:
        stmt = (
            select(Review.rating, func.count(Review.id))
            .where(Review.company_id == company_id)
            .group_by(Review.rating)
        )

        res = await session.execute(stmt)

        dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

        for rating, count in res.all():
            if rating in dist:
                dist[rating] = int(count)

        return {"distribution": dist}


# =====================================================
# API: Sentiment Series
# =====================================================
@router.get("/api/sentiment/series")
async def api_sentiment_series(
    company_id: int,
    start: str | None = None,
    end: str | None = None,
):
    start_date = parse_date(start)
    end_date = parse_date(end)

    async with get_session() as session:
        date_col = cast(Review.review_time, Date)

        stmt = select(
            date_col.label("date"),
            func.avg(Review.sentiment_score).label("value")
        ).where(Review.company_id == company_id)

        if start_date:
            stmt = stmt.where(date_col >= start_date)
        if end_date:
            stmt = stmt.where(date_col <= end_date)

        stmt = stmt.group_by(date_col).order_by(date_col)

        res = await session.execute(stmt)

        return {
            "series": [
                {"date": str(r.date), "value": round(float(r.value or 0), 3)}
                for r in res.all()
            ]
        }
