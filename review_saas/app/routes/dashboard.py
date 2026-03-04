# filename: app/routes/dashboard.py
from __future__ import annotations
import logging
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy import select, func, desc, cast, Date
from starlette.templating import Jinja2Templates

from app.core.db import get_session
from app.core.models import Company, Review
from app.routes.companies import _require_user

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.dashboard")

def parse_date(date_str: str | None):
    if not date_str: return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None

@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    uid = _require_user(request)
    if not uid:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Session expired."})
    return templates.TemplateResponse("dashboard.html", {"request": request})

@router.get("/api/kpis")
async def api_kpis(company_id: int, start: str | None = None, end: str | None = None):
    start_dt, end_dt = parse_date(start), parse_date(end)
    async with get_session() as session:
        # FIXED: Using google_review_time and sentiment_score to match Database
        stmt = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent")
        ).where(Review.company_id == company_id)

        if start_dt: stmt = stmt.where(cast(Review.google_review_time, Date) >= start_dt)
        if end_dt: stmt = stmt.where(cast(Review.google_review_time, Date) <= end_dt)

        res = await session.execute(stmt)
        stats = res.first()
        return {
            "total_reviews": int(stats.total or 0),
            "avg_rating": round(float(stats.avg_rating or 0.0), 2),
            "avg_sentiment": round(float(stats.avg_sent or 0.0), 3)
        }

@router.get("/api/reviews/list")
async def api_reviews_list(company_id: int, start: str | None = None, end: str | None = None):
    start_dt, end_dt = parse_date(start), parse_date(end)
    async with get_session() as session:
        # FIXED: Using google_review_time to match Database
        stmt = select(Review).where(Review.company_id == company_id)
        
        if start_dt: stmt = stmt.where(cast(Review.google_review_time, Date) >= start_dt)
        if end_dt: stmt = stmt.where(cast(Review.google_review_time, Date) <= end_dt)
        
        stmt = stmt.order_by(desc(Review.google_review_time)).limit(50)
        res = await session.execute(stmt)
        items = res.scalars().all()
        return {
            "items": [{
                "author_name": r.author_name or "Anonymous",
                "rating": r.rating,
                "text": r.text,
                "review_time": r.google_review_time.strftime("%Y-%m-%d") if r.google_review_time else ""
            } for r in items]
        }

@router.get("/api/series/reviews")
async def api_series_reviews(company_id: int):
    async with get_session() as session:
        date_col = cast(Review.google_review_time, Date)
        stmt = select(date_col.label("date"), func.count(Review.id).label("value")).where(Review.company_id == company_id).group_by("date").order_by("date")
        res = await session.execute(stmt)
        return {"series": [{"date": str(r.date), "value": r.value} for r in res.all()]}

@router.get("/api/sentiment/series")
async def api_sentiment_series(company_id: int):
    async with get_session() as session:
        date_col = cast(Review.google_review_time, Date)
        stmt = select(
            date_col.label("date"), 
            func.avg(Review.sentiment_score).label("value")
        ).where(Review.company_id == company_id).group_by("date").order_by("date")
        res = await session.execute(stmt)
        return {"series": [{"date": str(r.date), "value": round(float(r.value or 0), 3)} for r in res.all()]}
