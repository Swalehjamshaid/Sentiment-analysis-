# filename: app/routes/dashboard.py
from __future__ import annotations
from fastapi import APIRouter, Request, Query, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import select, func, cast, Date  # CRITICAL: Added cast and Date
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.core.db import get_session # Using your established session helper
from app.core.models import Company, Review
from app.services.google_reviews import ingest_company_reviews

router = APIRouter(tags=['dashboard'])
templates = Jinja2Templates(directory='app/templates')
logger = logging.getLogger(__name__)

def _require_user(request: Request):
    return request.session.get('user_id')

@router.get('/dashboard', response_class=HTMLResponse)
async def dashboard_page(request: Request, company_id: int | None = Query(None)):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse('/login', status_code=302)

    async with get_session() as session:
        # Load all companies for the dropdown menu
        result = await session.execute(select(Company).order_by(Company.name))
        companies = result.scalars().all()
        
        active_id = company_id
        if not active_id and companies:
            active_id = companies[0].id

        return templates.TemplateResponse('dashboard.html', {
            "request": request,
            "companies": companies,
            "active_company_id": active_id
        })

# ──────────────────────────────────────────────────────────────
# FIXED API ENDPOINTS (Corrected Date Casting & Column Names)
# ──────────────────────────────────────────────────────────────

@router.get('/api/kpis')
async def api_kpis(company_id: int, start: str | None = None, end: str | None = None):
    async with get_session() as session:
        # Mapping exactly to your models.py attributes
        q = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent")
        ).where(Review.company_id == company_id)

        # Apply cast to fix the 'toordinal' and 'operator does not exist' errors
        if start:
            q = q.where(func.date(Review.review_time) >= cast(start, Date))
        if end:
            q = q.where(func.date(Review.review_time) <= cast(end, Date))

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

        if start:
            stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end:
            stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))

        res = await session.execute(stmt)
        rows = res.all()
        return {"series": [{"date": str(r.date), "value": float(r.value or 0)} for r in rows]}

@router.get('/api/ratings/distribution')
async def api_ratings_distribution(company_id: int, start: str | None = None, end: str | None = None):
    async with get_session() as session:
        stmt = select(
            Review.rating,
            func.count(Review.id).label("count")
        ).where(Review.company_id == company_id).group_by(Review.rating).order_by(Review.rating)

        if start:
            stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end:
            stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))

        res = await session.execute(stmt)
        rows = res.all()
        
        dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for r in rows:
            dist[r.rating] = r.count
            
        return {"labels": ["1 Star", "2 Star", "3 Star", "4 Star", "5 Star"], "values": list(dist.values())}

@router.get('/api/series/reviews')
async def api_series_reviews(company_id: int, start: str | None = None, end: str | None = None):
    async with get_session() as session:
        stmt = select(
            func.date(Review.review_time).label("date"),
            func.count(Review.id).label("value")
        ).where(Review.company_id == company_id).group_by(func.date(Review.review_time)).order_by("date")

        if start:
            stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end:
            stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))

        res = await session.execute(stmt)
        rows = res.all()
        return {"series": [{"date": str(r.date), "value": int(r.value or 0)} for r in rows]}
