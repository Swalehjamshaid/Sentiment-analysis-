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

# Utility to parse dates for the charts
def parse_date(date_str: str | None):
    if not date_str: return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None

# --- UI Route ---
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    uid = _require_user(request)
    if not uid:
        # Redirect or show error if not logged in
        return templates.TemplateResponse("login.html", {"request": request, "error": "Please login first"})
    return templates.TemplateResponse("dashboard.html", {"request": request})

# --- API: Company List (REQUIRED for the dropdown) ---
@router.get("/api/companies/list")
async def api_companies_list(request: Request):
    uid = _require_user(request)
    if not uid: return {"companies": []}

    async with get_session() as session:
        stmt = select(Company.id, Company.name).where(Company.owner_id == uid).order_by(Company.name)
        res = await session.execute(stmt)
        return {"companies": [{"id": r.id, "name": r.name} for r in res.all()]}

# --- API: KPI Cards (REQUIRED to fix 404) ---
@router.get("/api/kpis")
async def api_kpis(request: Request, company_id: int, start: str | None = None, end: str | None = None):
    start_dt = parse_date(start)
    end_dt = parse_date(end)
    
    async with get_session() as session:
        stmt = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent")
        ).where(Review.company_id == company_id)

        if start_dt: stmt = stmt.where(cast(Review.review_time, Date) >= start_dt)
        if end_dt: stmt = stmt.where(cast(Review.review_time, Date) <= end_dt)

        res = await session.execute(stmt)
        stats = res.first()
        return {
            "total_reviews": int(stats.total or 0),
            "avg_rating": round(float(stats.avg_rating or 0.0), 2),
            "avg_sentiment": round(float(stats.avg_sent or 0.0), 3)
        }

# --- API: Reviews List (REQUIRED to fix 404) ---
@router.get("/api/reviews/list")
async def api_reviews_list(request: Request, company_id: int, start: str | None = None, end: str | None = None):
    start_dt = parse_date(start)
    end_dt = parse_date(end)

    async with get_session() as session:
        stmt = select(Review).where(Review.company_id == company_id)
        if start_dt: stmt = stmt.where(cast(Review.review_time, Date) >= start_dt)
        if end_dt: stmt = stmt.where(cast(Review.review_time, Date) <= end_dt)
        
        stmt = stmt.order_by(desc(Review.review_time)).limit(50)
        res = await session.execute(stmt)
        items = res.scalars().all()

        return {
            "items": [
                {
                    "author_name": r.author_name or "Anonymous",
                    "rating": r.rating,
                    "text": r.text,
                    "review_time": r.review_time.strftime("%Y-%m-%d") if r.review_time else ""
                } for r in items
            ]
        }

# --- API: Time Series (REQUIRED for Charts) ---
@router.get("/api/series/reviews")
async def api_series_reviews(company_id: int, start: str | None = None, end: str | None = None):
    async with get_session() as session:
        stmt = select(
            cast(Review.review_time, Date).label("date"),
            func.count(Review.id).label("value")
        ).where(Review.company_id == company_id).group_by("date").order_by("date")
        res = await session.execute(stmt)
        return {"series": [{"date": str(r.date), "value": r.value} for r in res.all()]}

@router.get("/api/ratings/distribution")
async def api_ratings_distribution(company_id: int):
    async with get_session() as session:
        stmt = select(Review.rating, func.count(Review.id)).where(Review.company_id == company_id).group_by(Review.rating)
        res = await session.execute(stmt)
        dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for r in res.all(): dist[int(r[0])] = r[1]
        return {"distribution": dist}

@router.get("/api/sentiment/series")
async def api_sentiment_series(company_id: int):
    async with get_session() as session:
        stmt = select(
            cast(Review.review_time, Date).label("date"),
            func.avg(Review.sentiment_score).label("value")
        ).where(Review.company_id == company_id).group_by("date").order_by("date")
        res = await session.execute(stmt)
        return {"series": [{"date": str(r.date), "value": round(float(r.value or 0), 3)} for r in res.all()]}
