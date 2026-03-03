# filename: app/routes/dashboard.py
from __future__ import annotations
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import select, func, cast, Date # CRITICAL: added cast and Date
import logging

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(tags=['dashboard'])
templates = Jinja2Templates(directory='app/templates')

@router.get('/api/kpis')
async def api_kpis(company_id: int, start: str | None = None, end: str | None = None):
    async with get_session() as session:
        q = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent")
        ).where(Review.company_id == company_id)

        # CAST handles the mismatch between HTML text input and Postgres Date type
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
        stmt = select(Review.rating, func.count(Review.id)).where(Review.company_id == company_id).group_by(Review.rating)
        
        if start: stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end: stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))
        
        res = await session.execute(stmt)
        dist = {1:0, 2:0, 3:0, 4:0, 5:0}
        for r in res.all(): dist[r[0]] = r[1]
        return {"labels": ["1 Star", "2 Star", "3 Star", "4 Star", "5 Star"], "values": list(dist.values())}
