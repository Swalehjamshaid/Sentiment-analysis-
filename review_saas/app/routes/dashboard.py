# filename: app/routes/dashboard.py
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import select, func, cast, Date

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(tags=['dashboard'])
templates = Jinja2Templates(directory='app/templates')
logger = logging.getLogger("app.dashboard")

# --- UI ROUTE ---

@router.get('/dashboard', response_class=HTMLResponse)
async def get_dashboard(request: Request, company_id: int | None = None):
    async with get_session() as session:
        # If no company_id is provided, try to fetch the first available one
        if not company_id:
            first_comp = await session.execute(select(Company).limit(1))
            company = first_comp.scalar_one_or_none()
        else:
            res = await session.execute(select(Company).where(Company.id == company_id))
            company = res.scalar_one_or_none()
        
        # Fetch all companies for the dropdown selector
        all_comps_res = await session.execute(select(Company))
        all_companies = all_comps_res.scalars().all()
            
        return templates.TemplateResponse(
            "dashboard.html", 
            {
                "request": request, 
                "company": company, 
                "all_companies": all_companies
            }
        )

# --- API ENDPOINTS ---

@router.get('/api/kpis')
async def api_kpis(company_id: int, start: str | None = None, end: str | None = None):
    async with get_session() as session:
        # Calculate time 24 hours ago for the 'New (24h)' metric
        day_ago = datetime.now() - timedelta(hours=24)

        # Main Stats Query
        q = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent")
        ).where(Review.company_id == company_id)

        # 24h New Reviews Query
        new_q = select(func.count(Review.id)).where(
            Review.company_id == company_id,
            Review.review_time >= day_ago
        )

        if start: q = q.where(func.date(Review.review_time) >= cast(start, Date))
        if end: q = q.where(func.date(Review.review_time) <= cast(end, Date))

        res = await session.execute(q)
        stats = res.fetchone()
        
        new_res = await session.execute(new_q)
        new_count = new_res.scalar() or 0
        
        return {
            "total_reviews": stats.total or 0,
            "avg_rating": round(float(stats.avg_rating or 0), 2),
            "avg_sentiment": round(float(stats.avg_sent or 0), 3),
            "new_24h": new_count
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
        stmt = select(Review.rating, func.count(Review.id)).where(Review.company_id == company_id).group_by(Review.rating)
        
        if start: stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end: stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))
        
        res = await session.execute(stmt)
        dist = {1:0, 2:0, 3:0, 4:0, 5:0}
        for r in res.all():
            if r[0] in dist: dist[r[0]] = r[1]
            
        return {
            "labels": ["1 Star", "2 Star", "3 Star", "4 Star", "5 Star"], 
            "values": list(dist.values())
        }
