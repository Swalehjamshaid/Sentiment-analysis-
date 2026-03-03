# filename: app/routes/dashboard.py
from __future__ import annotations
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import select, func
from datetime import datetime, timedelta
import logging

from app.core.db import get_session
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
        from fastapi.responses import RedirectResponse
        return RedirectResponse('/login', status_code=302)

    async with get_session() as session:
        # Load all companies for the dropdown
        result = await session.execute(select(Company).order_by(Company.name))
        companies = result.scalars().all()
        
        active_company_id = company_id
        if not active_company_id and companies:
            active_company_id = companies[0].id

        return templates.TemplateResponse('dashboard.html', {
            "request": request,
            "companies": companies,
            "active_company_id": active_company_id
        })

# ──────────────────────────────────────────────────────────────
# FIXED API ENDPOINTS (Using sentiment_score instead of sentiment_compound)
# ──────────────────────────────────────────────────────────────

@router.get('/api/kpis')
async def api_kpis(company_id: int, start: str | None = None, end: str | None = None):
    async with get_session() as session:
        # Fixed: Using sentiment_score to match models.py
        q = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent")
        ).where(Review.company_id == company_id)

        if start:
            q = q.where(func.date(Review.review_time) >= start)
        if end:
            q = q.where(func.date(Review.review_time) <= end)

        res = await session.execute(q)
        stats = res.fetchone()

        return {
            "total_reviews": stats.total or 0,
            "avg_rating": float(stats.avg_rating or 0),
            "avg_sentiment": float(stats.avg_sent or 0)
        }

@router.get('/api/sentiment/series')
async def api_sentiment_series(company_id: int, start: str | None = None, end: str | None = None):
    async with get_session() as session:
        # Fixed: Using sentiment_score to match models.py
        stmt = select(
            func.date(Review.review_time).label("date"),
            func.avg(Review.sentiment_score).label("value")
        ).where(Review.company_id == company_id).group_by(func.date(Review.review_time)).order_by("date")

        if start:
            stmt = stmt.where(func.date(Review.review_time) >= start)
        if end:
            stmt = stmt.where(func.date(Review.review_time) <= end)

        res = await session.execute(stmt)
        rows = res.all()
        return {"series": [{"date": str(r.date), "value": float(r.value or 0)} for r in rows]}

@router.get('/api/reviews/summary/{company_id}')
async def api_review_summary(company_id: int, refresh: bool = False):
    """
    Unified endpoint for the dashboard to trigger a sync and get KPIs
    """
    async with get_session() as session:
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Automatically fetch from Google if refresh is True or data is missing
        if refresh or not company.last_updated:
            try:
                await ingest_company_reviews(session, company)
            except Exception as e:
                logger.error(f"Sync failed: {e}")

        # Return latest KPIs
        q = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent")
        ).where(Review.company_id == company_id)
        
        res = await session.execute(q)
        stats = res.fetchone()

        return {
            "total_reviews": stats.total or 0,
            "avg_rating": float(stats.avg_rating or 0),
            "avg_sentiment": float(stats.avg_sent or 0)
        }
