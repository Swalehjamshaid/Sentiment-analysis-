# filename: app/routes/dashboard.py
from __future__ import annotations
import logging
from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, desc, asc, cast, Date, or_
from starlette.templating import Jinja2Templates
from app.core.db import get_session
from app.core.models import Company, Review, AIResponse, User

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.dashboard")

def parse_date(date_str: str | None) -> datetime.date | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception as e:
        logger.warning(f"Invalid date format: {date_str} - {e}")
        return None

@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

# =====================================================
# Company List - Filtered by Owner (Req 39, 42)
# =====================================================
@router.get("/api/companies/list")
async def api_companies_list(owner_id: int):
    async with get_session() as session:
        # Only show companies belonging to the logged-in user
        stmt = select(Company).where(Company.owner_id == owner_id).order_by(Company.name)
        result = await session.execute(stmt)
        companies = result.scalars().all()
        return {
            "companies": [
                {
                    "id": c.id, 
                    "name": c.name, 
                    "city": c.location_city, 
                    "status": c.status
                } for c in companies
            ]
        }

# =====================================================
# KPI Cards (Req 98)
# =====================================================
@router.get("/api/kpis")
async def api_kpis(company_id: int, start: str | None = None, end: str | None = None):
    start_dt = parse_date(start)
    end_dt = parse_date(end)

    async with get_session() as session:
        stmt = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent"),
        ).where(Review.company_id == company_id)

        if start_dt:
            stmt = stmt.where(cast(Review.review_time, Date) >= start_dt)
        if end_dt:
            stmt = stmt.where(cast(Review.review_time, Date) <= end_dt)

        res = await session.execute(stmt)
        stats = res.first()

        return {
            "total_reviews": int(stats.total or 0),
            "avg_rating": round(float(stats.avg_rating or 0.0), 2),
            "avg_sentiment": round(float(stats.avg_sent or 0.0), 3),
        }

# =====================================================
# Reviews List with AI Suggestions (Req 85, 99)
# =====================================================
@router.get("/api/reviews/list")
async def api_reviews_list(
    company_id: int, 
    start: str | None = None, 
    end: str | None = None, 
    sort: str = "newest"
):
    start_dt = parse_date(start)
    end_dt = parse_date(end)

    async with get_session() as session:
        stmt = select(Review).where(Review.company_id == company_id)

        if start_dt:
            stmt = stmt.where(cast(Review.review_time, Date) >= start_dt)
        if end_dt:
            stmt = stmt.where(cast(Review.review_time, Date) <= end_dt)

        if sort == "newest": stmt = stmt.order_by(desc(Review.review_time))
        elif sort == "oldest": stmt = stmt.order_by(asc(Review.review_time))
        elif sort == "highest": stmt = stmt.order_by(desc(Review.rating))
        elif sort == "lowest": stmt = stmt.order_by(asc(Review.rating))

        res = await session.execute(stmt.limit(50))
        reviews = res.scalars().all()

        output = []
        for r in reviews:
            # Check for existing AI suggested reply
            reply_stmt = select(AIResponse).where(AIResponse.review_id == r.id)
            reply_res = await session.execute(reply_stmt)
            reply = reply_res.scalar_one_or_none()

            output.append({
                "id": r.id,
                "author_name": r.author_name or "Anonymous",
                "rating": int(r.rating or 0),
                "text": r.text or "",
                "sentiment": r.sentiment_category,
                "review_time": r.review_time.strftime("%Y-%m-%d %H:%M") if r.review_time else "",
                "ai_reply_suggestion": reply.suggested_text if reply else None,
                "reply_status": reply.status if reply else "Pending"
            })

        return {"items": output}

# =====================================================
# Reviews Time Series (Req 100)
# =====================================================
@router.get("/api/series/reviews")
async def api_series_reviews(company_id: int, start: str | None = None, end: str | None = None):
    start_dt = parse_date(start)
    end_dt = parse_date(end)

    async with get_session() as session:
        date_col = cast(Review.review_time, Date)
        stmt = select(date_col.label("date"), func.count(Review.id).label("value")).where(Review.company_id == company_id)

        if start_dt: stmt = stmt.where(date_col >= start_dt)
        if end_dt: stmt = stmt.where(date_col <= end_dt)

        stmt = stmt.group_by(date_col).order_by(date_col)
        res = await session.execute(stmt)

        return {"series": [{"date": str(r.date), "value": int(r.value or 0)} for r in res.all()]}

# =====================================================
# Ratings Distribution (Req 98)
# =====================================================
@router.get("/api/ratings/distribution")
async def api_ratings_distribution(company_id: int):
    async with get_session() as session:
        stmt = select(Review.rating, func.count(Review.id)).where(Review.company_id == company_id).group_by(Review.rating)
        res = await session.execute(stmt)
        dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for rating, count in res.all():
            if rating in dist: dist[int(rating)] = int(count or 0)
        return {"distribution": dist}

# =====================================================
# Sentiment Series (Req 76)
# =====================================================
@router.get("/api/sentiment/series")
async def api_sentiment_series(company_id: int, start: str | None = None, end: str | None = None):
    start_dt = parse_date(start)
    end_dt = parse_date(end)

    async with get_session() as session:
        date_col = cast(Review.review_time, Date)
        stmt = select(date_col.label("date"), func.avg(Review.sentiment_score).label("value")).where(Review.company_id == company_id)

        if start_dt: stmt = stmt.where(date_col >= start_dt)
        if end_dt: stmt = stmt.where(date_col <= end_dt)

        stmt = stmt.group_by(date_col).order_by(date_col)
        res = await session.execute(stmt)

        return {"series": [{"date": str(r.date), "value": round(float(r.value or 0), 3)} for r in res.all()]}

# =====================================================
# Full Production Debug Route
# =====================================================
@router.get("/api/debug/full-check")
async def debug_full_check():
    async with get_session() as session:
        stmt = (
            select(Company.id, Company.name, Company.owner_id, func.count(Review.id).label("count"))
            .outerjoin(Review, Company.id == Review.company_id)
            .group_by(Company.id, Company.name, Company.owner_id)
        )
        res = await session.execute(stmt)
        return [{"id": r.id, "name": r.name, "owner": r.owner_id, "reviews": r.count} for r in res.all()]
