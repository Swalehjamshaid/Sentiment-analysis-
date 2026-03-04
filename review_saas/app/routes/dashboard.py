# filename: app/routes/dashboard.py
from __future__ import annotations
import logging
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, desc, asc, cast, Date
from starlette.templating import Jinja2Templates
from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.dashboard")


# =====================================================
# Safe Date Parser
# =====================================================
def parse_date(date_str: str | None) -> datetime.date | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception as e:
        logger.warning(f"Invalid date format: {date_str} - {e}")
        return None


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
# Company List
# =====================================================
@router.get("/api/companies/list")
async def api_companies_list():
    async with get_session() as session:
        stmt = select(Company.id, Company.name).order_by(Company.name)
        result = await session.execute(stmt)
        companies = result.all()
        return {
            "companies": [
                {"id": int(c.id), "name": c.name}
                for c in companies
            ]
        }


# =====================================================
# KPI Cards
# =====================================================
@router.get("/api/kpis")
async def api_kpis(
    company_id: int,
    start: str | None = None,
    end: str | None = None,
):
    start_dt = parse_date(start)
    end_dt = parse_date(end)

    async with get_session() as session:
        stmt = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent"),
        ).where(Review.company_id == company_id)

        if start_dt:
            stmt = stmt.where(cast(Review.google_review_time, Date) >= start_dt)
        if end_dt:
            stmt = stmt.where(cast(Review.google_review_time, Date) <= end_dt)

        res = await session.execute(stmt)
        stats = res.first()

        total = int(stats.total or 0) if stats else 0
        avg_rating = float(stats.avg_rating or 0.0) if stats else 0.0
        avg_sent = float(stats.avg_sent or 0.0) if stats else 0.0

        return {
            "total_reviews": total,
            "avg_rating": round(avg_rating, 2),
            "avg_sentiment": round(avg_sent, 3),
        }


# =====================================================
# Reviews List
# =====================================================
@router.get("/api/reviews/list")
async def api_reviews_list(
    company_id: int,
    start: str | None = None,
    end: str | None = None,
    sort: str = "newest",
):
    start_dt = parse_date(start)
    end_dt = parse_date(end)

    async with get_session() as session:
        stmt = select(Review).where(Review.company_id == company_id)

        if start_dt:
            stmt = stmt.where(cast(Review.google_review_time, Date) >= start_dt)
        if end_dt:
            stmt = stmt.where(cast(Review.google_review_time, Date) <= end_dt)

        # Sorting
        if sort == "newest":
            stmt = stmt.order_by(desc(Review.google_review_time))
        elif sort == "oldest":
            stmt = stmt.order_by(asc(Review.google_review_time))
        elif sort == "highest":
            stmt = stmt.order_by(desc(Review.rating))
        elif sort == "lowest":
            stmt = stmt.order_by(asc(Review.rating))

        res = await session.execute(stmt.limit(50))
        reviews = res.scalars().all()

        return {
            "items": [
                {
                    "author_name": r.author_name or "Anonymous",
                    "rating": int(r.rating or 0),
                    "text": r.text or "",
                    "review_time": (
                        r.google_review_time.strftime("%Y-%m-%d %H:%M")
                        if r.google_review_time
                        else ""
                    ),
                }
                for r in reviews
            ]
        }


# =====================================================
# Reviews Time Series
# =====================================================
@router.get("/api/series/reviews")
async def api_series_reviews(
    company_id: int,
    start: str | None = None,
    end: str | None = None,
):
    start_dt = parse_date(start)
    end_dt = parse_date(end)

    async with get_session() as session:
        date_col = cast(Review.google_review_time, Date)
        stmt = select(
            date_col.label("date"),
            func.count(Review.id).label("value"),
        ).where(Review.company_id == company_id)

        if start_dt:
            stmt = stmt.where(date_col >= start_dt)
        if end_dt:
            stmt = stmt.where(date_col <= end_dt)

        stmt = stmt.group_by(date_col).order_by(date_col)
        res = await session.execute(stmt)

        return {
            "series": [
                {
                    "date": str(r.date),
                    "value": int(r.value or 0),
                }
                for r in res.all()
            ]
        }


# =====================================================
# Ratings Distribution
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
                dist[int(rating)] = int(count or 0)
        return {"distribution": dist}


# =====================================================
# Sentiment Series
# =====================================================
@router.get("/api/sentiment/series")
async def api_sentiment_series(
    company_id: int,
    start: str | None = None,
    end: str | None = None,
):
    start_dt = parse_date(start)
    end_dt = parse_date(end)

    async with get_session() as session:
        date_col = cast(Review.google_review_time, Date)
        stmt = select(
            date_col.label("date"),
            func.avg(Review.sentiment_score).label("value"),
        ).where(Review.company_id == company_id)

        if start_dt:
            stmt = stmt.where(date_col >= start_dt)
        if end_dt:
            stmt = stmt.where(date_col <= end_dt)

        stmt = stmt.group_by(date_col).order_by(date_col)
        res = await session.execute(stmt)

        return {
            "series": [
                {
                    "date": str(r.date),
                    "value": round(float(r.value or 0), 3),
                }
                for r in res.all()
            ]
        }


# =====================================================
# Debug Route – useful to check if data exists
# =====================================================
@router.get("/api/debug/company-check")
async def debug_company_check():
    async with get_session() as session:
        stmt = (
            select(
                Company.id,
                Company.name,
                func.count(Review.id).label("review_count"),
            )
            .outerjoin(Review, Company.id == Review.company_id)
            .group_by(Company.id, Company.name)
        )
        res = await session.execute(stmt)
        return [
            {
                "id": int(r.id),
                "name": r.name,
                "review_count": int(r.review_count or 0),
            }
            for r in res.all()
        ]
