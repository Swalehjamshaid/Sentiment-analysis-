# filename: app/routes/dashboard.py
from __future__ import annotations
import logging
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import select, func, cast, Date

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(tags=['dashboard'])
templates = Jinja2Templates(directory='app/templates')

# --- UI ROUTES ---

@router.get('/dashboard', response_class=HTMLResponse)
async def get_dashboard(request: Request, company_id: int = 1):
    """
    Renders the main dashboard HTML page.
    This fixes the 404 error seen after the /login redirect.
    """
    async with get_session() as session:
        # Validate company exists
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        
        if not company:
            # Fallback or redirect if no company found
            return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
            
        return templates.TemplateResponse(
            "dashboard.html", 
            {"request": request, "company": company}
        )

# --- JSON API ROUTES ---

@router.get('/api/kpis')
async def api_kpis(company_id: int, start: str | None = None, end: str | None = None):
    async with get_session() as session:
        q = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent")
        ).where(Review.company_id == company_id)

        # CAST handles the mismatch between HTML text input strings and DB Date types
        if start: q = q.where(func.date(Review.review_time) >= cast(start, Date))
        if end: q = q.where(func.date(Review.review_time) <= cast(end, Date))

        res = await session.execute(q)
        stats = res.fetchone()
        
        return {
            "total_reviews": stats.total or 0,
            "avg_rating": round(float(stats.avg_rating or 0), 2),
            "avg_sentiment": round(float(stats.avg_sent or 0), 3)
        }

@router.get('/api/sentiment/series')
async def api_sentiment_series(company_id: int, start: str | None = None, end: str | None = None):
    async with get_session() as session:
        stmt = select(
            func.date(Review.review_time).label("date"), 
            func.avg(Review.sentiment_score).label("value")
        ).where(Review.company_id == company_id).group_by(func.date(Review.review_time)).order_by("date")
        
        if start: stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end: stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))
        
        res = await session.execute(stmt)
        return {"series": [{"date": str(r.date), "value": float(r.value or 0)} for r in res.all()]}

@router.get('/api/ratings/distribution')
async def api_ratings_distribution(company_id: int, start: str | None = None, end: str | None = None):
    async with get_session() as session:
        stmt = select(
            Review.rating, 
            func.count(Review.id)
        ).where(Review.company_id == company_id).group_by(Review.rating)
        
        if start: stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end: stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))
        
        res = await session.execute(stmt)
        
        # Initialize dictionary to ensure all 5 stars are represented even if count is 0
        dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for r in res.all():
            dist[r[0]] = r[1]
            
        return {
            "labels": ["1 Star", "2 Star", "3 Star", "4 Star", "5 Star"], 
            "values": [dist[1], dist[2], dist[3], dist[4], dist[5]]
        }
