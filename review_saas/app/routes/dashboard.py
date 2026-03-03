# filename: app/routes/dashboard.py
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
# Added 'cast' and 'Date' to handle Postgres timezone-aware comparisons
from sqlalchemy import select, func, desc, asc, cast, Date

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(tags=['dashboard'])
templates = Jinja2Templates(directory='app/templates')
logger = logging.getLogger("app.dashboard")

# --- UTILITY: parse dates ---
def parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        # Standardize conversion to date object for SQL compatibility
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {date_str}. Use YYYY-MM-DD")

# --- UI ROUTE ---
@router.get('/dashboard', response_class=HTMLResponse)
async def get_dashboard(request: Request, company_id: int | None = None):
    return templates.TemplateResponse("dashboard.html", {"request": request})

# --- API: COMPANY LIST ---
@router.get('/api/companies/list')
async def api_companies_list():
    async with get_session() as session:
        stmt = select(Company.id, Company.name).order_by(Company.name)
        result = await session.execute(stmt)
        companies = result.all()
        return {"companies": [{"id": c.id, "name": c.name} for c in companies]}

# --- API: KPI CARDS ---
@router.get('/api/kpis')
async def api_kpis(company_id: int, start: str | None = None, end: str | None = None):
    start_date = parse_date(start)
    end_date = parse_date(end)

    async with get_session() as session:
        q = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent")
        ).where(Review.company_id == company_id)

        # FIXED: Cast Review.review_time to Date for accurate filtering against dashboard strings
        if start_date:
            q = q.where(cast(Review.review_time, Date) >= start_date.date())
        if end_date:
            q = q.where(cast(Review.review_time, Date) <= end_date.date())

        res = await session.execute(q)
        stats = res.fetchone()

        return {
            "total_reviews": stats.total or 0,
            "avg_rating": round(float(stats.avg_rating or 0.0), 2),
            "avg_sentiment": round(float(stats.avg_sent or 0.0), 3)
        }

# --- API: REVIEW LIST ---
@router.get('/api/reviews/list')
async def api_reviews_list(
    company_id: int, 
    sort: str = "newest", 
    start: str | None = None, 
    end: str | None = None
):
    start_date = parse_date(start)
    end_date = parse_date(end)

    async with get_session() as session:
        stmt = select(Review).where(Review.company_id == company_id)

        if sort == "newest": stmt = stmt.order_by(desc(Review.review_time))
        elif sort == "oldest": stmt = stmt.order_by(asc(Review.review_time))
        elif sort == "highest": stmt = stmt.order_by(desc(Review.rating))
        elif sort == "lowest": stmt = stmt.order_by(asc(Review.rating))

        # FIXED: Cast to Date to ignore database time/timezone offsets
        if start_date:
            stmt = stmt.where(cast(Review.review_time, Date) >= start_date.date())
        if end_date:
            stmt = stmt.where(cast(Review.review_time, Date) <= end_date.date())

        res = await session.execute(stmt.limit(50))
        items = res.scalars().all()

        return {
            "items": [
                {
                    "author_name": r.author_name or "Anonymous",
                    "rating": r.rating,
                    "text": r.text,
                    "review_time": r.review_time.strftime("%Y-%m-%d %H:%M") if r.review_time else ""
                } for r in items
            ]
        }

# --- API: CHART DATA ---
@router.get('/api/series/reviews')
async def api_series_reviews(company_id: int, start: str | None = None, end: str | None = None):
    start_date = parse_date(start)
    end_date = parse_date(end)

    async with get_session() as session:
        stmt = select(
            func.date(Review.review_time).label("date"), 
            func.count(Review.id).label("value")
        ).where(Review.company_id == company_id)

        if start_date:
            stmt = stmt.where(cast(Review.review_time, Date) >= start_date.date())
        if end_date:
            stmt = stmt.where(cast(Review.review_time, Date) <= end_date.date())

        stmt = stmt.group_by(func.date(Review.review_time)).order_by("date")
        res = await session.execute(stmt)

        return {"series": [{"date": str(r.date), "value": int(r.value or 0)} for r in res.all()]}

@router.get('/api/ratings/distribution')
async def api_ratings_distribution(company_id: int):
    async with get_session() as session:
        stmt = select(Review.rating, func.count(Review.id)).where(Review.company_id == company_id).group_by(Review.rating)
        res = await session.execute(stmt)
        dist = {1:0, 2:0, 3:0, 4:0, 5:0}
        for r in res.all():
            if r[0] in dist: dist[r[0]] = r[1]
        return {"distribution": dist}

@router.get('/api/sentiment/series')
async def api_sentiment_series(company_id: int, start: str | None = None, end: str | None = None):
    start_date = parse_date(start)
    end_date = parse_date(end)

    async with get_session() as session:
        stmt = select(
            func.date(Review.review_time).label("date"), 
            func.avg(Review.sentiment_score).label("value")
        ).where(Review.company_id == company_id)

        if start_date:
            stmt = stmt.where(cast(Review.review_time, Date) >= start_date.date())
        if end_date:
            stmt = stmt.where(cast(Review.review_time, Date) <= end_date.date())

        stmt = stmt.group_by(func.date(Review.review_time)).order_by("date")
        res = await session.execute(stmt)

        return {"series": [{"date": str(r.date), "value": float(r.value or 0)} for r in res.all()]}
