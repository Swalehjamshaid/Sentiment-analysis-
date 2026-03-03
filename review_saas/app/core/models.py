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

# Initialize router and templates
router = APIRouter(tags=['dashboard'])
templates = Jinja2Templates(directory='app/templates')
logger = logging.getLogger("app.dashboard")

# --- UI ROUTE (Renders the Dashboard Page) ---

@router.get('/dashboard', response_class=HTMLResponse)
async def get_dashboard(request: Request, company_id: int | None = None):
    """
    Renders the dashboard. If no company_id is provided, it attempts to
    default to the first company found in the database.
    """
    async with get_session() as session:
        # 1. Fetch all companies to populate the "Company" dropdown in your UI
        all_comps_stmt = select(Company).order_by(Company.name)
        all_comps_res = await session.execute(all_comps_stmt)
        all_companies = all_comps_res.scalars().all()

        # 2. Determine which company is currently selected
        selected_company = None
        if company_id:
            res = await session.execute(select(Company).where(Company.id == company_id))
            selected_company = res.scalar_one_or_none()
        elif all_companies:
            selected_company = all_companies[0]

        return templates.TemplateResponse(
            "dashboard.html", 
            {
                "request": request, 
                "company": selected_company,
                "all_companies": all_companies
            }
        )

# --- API ENDPOINTS (Called by the 'Fetch Data' button in your UI) ---

@router.get('/api/kpis')
async def api_kpis(
    company_id: int, 
    start: str | None = Query(None), 
    end: str | None = Query(None)
):
    async with get_session() as session:
        # Time threshold for the "New (24h)" card in your screenshot
        last_24h = datetime.now() - timedelta(hours=24)

        # Query for Main Stats
        stats_stmt = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent")
        ).where(Review.company_id == company_id)

        # Query for 'New (24h)' count
        new_stmt = select(func.count(Review.id)).where(
            Review.company_id == company_id,
            Review.review_time >= last_24h
        )

        # Apply Date Filters if provided from the UI date pickers
        if start:
            stats_stmt = stats_stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end:
            stats_stmt = stats_stmt.where(func.date(Review.review_time) <= cast(end, Date))

        # Execute
        stats_res = await session.execute(stats_stmt)
        stats = stats_res.fetchone()
        
        new_res = await session.execute(new_stmt)
        new_count = new_res.scalar() or 0
        
        return {
            "total_reviews": stats.total or 0,
            "avg_rating": round(float(stats.avg_rating or 0.0), 1),
            "avg_sentiment": round(float(stats.avg_sent or 0.0), 3),
            "new_24h": new_count
        }

@router.get('/api/sentiment/series')
async def api_sentiment_series(
    company_id: int, 
    start: str | None = Query(None), 
    end: str | None = Query(None)
):
    async with get_session() as session:
        stmt = select(
            func.date(Review.review_time).label("date"), 
            func.avg(Review.sentiment_score).label("value")
        ).where(Review.company_id == company_id).group_by(func.date(Review.review_time)).order_by("date")
        
        if start:
            stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end:
            stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))
        
        res = await session.execute(stmt)
        return {"series": [{"date": str(r.date), "value": float(r.value or 0)} for r in res.all()]}

@router.get('/api/ratings/distribution')
async def api_ratings_distribution(
    company_id: int, 
    start: str | None = Query(None), 
    end: str | None = Query(None)
):
    async with get_session() as session:
        stmt = select(
            Review.rating, 
            func.count(Review.id)
        ).where(Review.company_id == company_id).group_by(Review.rating)
        
        if start:
            stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end:
            stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))
        
        res = await session.execute(stmt)
        
        # Mapping to ensure all 1-5 stars are represented in the chart
        dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for r in res.all():
            if r[0] in dist:
                dist[r[0]] = r[1]
            
        return {
            "labels": ["1 Star", "2 Star", "3 Star", "4 Star", "5 Star"], 
            "values": [dist[1], dist[2], dist[3], dist[4], dist[5]]
        }
