# filename: app/routes/dashboard.py
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import select, func, cast, Date, desc, asc

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(tags=['dashboard'])
templates = Jinja2Templates(directory='app/templates')
logger = logging.getLogger("app.dashboard")

# --- UI ROUTE ---

@router.get('/dashboard', response_class=HTMLResponse)
async def get_dashboard(request: Request, company_id: int | None = None):
    async with get_session() as session:
        # Fetch all companies for the dropdown selector
        all_comps_res = await session.execute(select(Company).order_by(Company.name))
        all_companies = all_comps_res.scalars().all()

        # Match active selection
        active_id = company_id
        if not active_id and all_companies:
            active_id = all_companies[0].id

        return templates.TemplateResponse(
            "dashboard.html", 
            {
                "request": request, 
                "companies": all_companies,
                "active_company_id": active_id
            }
        )

# --- API ENDPOINTS (Aligned with your HTML JavaScript) ---

@router.get('/api/kpis')
async def api_kpis(company_id: int, start: str | None = None, end: str | None = None):
    async with get_session() as session:
        q = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent")
        ).where(Review.company_id == company_id)

        if start: q = q.where(func.date(Review.review_time) >= cast(start, Date))
        if end: q = q.where(func.date(Review.review_time) <= cast(end, Date))

        res = await session.execute(q)
        stats = res.fetchone()
        
        return {
            "total_reviews": stats.total or 0,
            "avg_rating": float(stats.avg_rating or 0),
            "avg_sentiment": float(stats.avg_sent or 0)
        }

@router.get('/api/series/reviews')
async def api_series_reviews(company_id: int, start: str | None = None, end: str | None = None):
    """Populates the 'Reviews per day' chart."""
    async with get_session() as session:
        stmt = select(
            func.date(Review.review_time).label("date"), 
            func.count(Review.id).label("value")
        ).where(Review.company_id == company_id).group_by(func.date(Review.review_time)).order_by("date")
        
        if start: stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end: stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))
        
        res = await session.execute(stmt)
        return {"series": [{"date": str(r.date), "value": int(r.value or 0)} for r in res.all()]}

@router.get('/api/ratings/distribution')
async def api_ratings_distribution(company_id: int, start: str | None = None, end: str | None = None):
    """Populates the 'Ratings distribution' bar chart."""
    async with get_session() as session:
        stmt = select(Review.rating, func.count(Review.id)).where(Review.company_id == company_id).group_by(Review.rating)
        
        if start: stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end: stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))
        
        res = await session.execute(stmt)
        dist = {1:0, 2:0, 3:0, 4:0, 5:0}
        for r in res.all():
            if r[0] in dist: dist[r[0]] = r[1]
        return {"distribution": dist}

@router.get('/api/sentiment/series')
async def api_sentiment_series(company_id: int, start: str | None = None, end: str | None = None):
    """Populates the 'Avg sentiment per day' chart."""
    async with get_session() as session:
        stmt = select(
            func.date(Review.review_time).label("date"), 
            func.avg(Review.sentiment_score).label("value")
        ).where(Review.company_id == company_id).group_by(func.date(Review.review_time)).order_by("date")
        
        if start: stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end: stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))
        
        res = await session.execute(stmt)
        return {"series": [{"date": str(r.date), "value": float(r.value or 0)} for r in res.all()]}

@router.get('/api/reviews/list')
async def api_reviews_list(
    company_id: int, 
    sort: str = "newest", 
    start: str | None = None, 
    end: str | None = None
):
    """Populates the scrollable reviews list at the bottom."""
    async with get_session() as session:
        stmt = select(Review).where(Review.company_id == company_id)
        
        # Sorting logic
        if sort == "newest": stmt = stmt.order_by(desc(Review.review_time))
        elif sort == "oldest": stmt = stmt.order_by(asc(Review.review_time))
        elif sort == "highest": stmt = stmt.order_by(desc(Review.rating))
        elif sort == "lowest": stmt = stmt.order_by(asc(Review.rating))

        if start: stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end: stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))

        res = await session.execute(stmt.limit(50))
        items = res.scalars().all()
        
        return {
            "items": [
                {
                    "author_name": i.author_name,
                    "rating": i.rating,
                    "text": i.text,
                    "review_time": i.review_time.strftime("%Y-%m-%d") if i.review_time else ""
                } for i in items
            ]
        }
