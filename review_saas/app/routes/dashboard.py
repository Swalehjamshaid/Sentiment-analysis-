# filename: app/routes/dashboard.py
from __future__ import annotations
import logging
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import select, func, cast, Date, desc, asc

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.dashboard")


# -------------------------------------------------
# DASHBOARD PAGE
# -------------------------------------------------
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request, company_id: int | None = None):

    # ✅ Get logged-in user
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with get_session() as session:

        # ✅ Fetch only companies owned by this user
        stmt = (
            select(Company.id, Company.name)
            .where(Company.owner_id == user_id)
            .order_by(Company.name)
        )

        result = await session.execute(stmt)
        rows = result.all()

        # Convert into clean list
        companies = [{"id": r.id, "name": r.name} for r in rows]

        if not companies:
            return templates.TemplateResponse(
                "dashboard.html",
                {
                    "request": request,
                    "companies": [],
                    "active_company_id": None,
                    "error": "No companies found. Please add a company first.",
                },
            )

        active_id = company_id or companies[0]["id"]

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "companies": companies,
                "active_company_id": active_id,
            },
        )


# -------------------------------------------------
# KPI API
# -------------------------------------------------
@router.get("/api/kpis")
async def api_kpis(company_id: int, start: str | None = None, end: str | None = None):

    async with get_session() as session:

        q = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent"),
        ).where(Review.company_id == company_id)

        if start:
            q = q.where(func.date(Review.review_time) >= cast(start, Date))
        if end:
            q = q.where(func.date(Review.review_time) <= cast(end, Date))

        res = await session.execute(q)
        stats = res.fetchone()

        return {
            "total_reviews": stats.total or 0,
            "avg_rating": round(float(stats.avg_rating or 0), 1),
            "avg_sentiment": round(float(stats.avg_sent or 0), 3),
        }


# -------------------------------------------------
# REVIEWS PER DAY
# -------------------------------------------------
@router.get("/api/series/reviews")
async def api_series_reviews(company_id: int, start: str | None = None, end: str | None = None):

    async with get_session() as session:

        stmt = (
            select(
                func.date(Review.review_time).label("date"),
                func.count(Review.id).label("value"),
            )
            .where(Review.company_id == company_id)
            .group_by(func.date(Review.review_time))
            .order_by(func.date(Review.review_time))
        )

        if start:
            stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end:
            stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))

        res = await session.execute(stmt)

        return {
            "series": [
                {"date": str(r.date), "value": int(r.value or 0)}
                for r in res.all()
            ]
        }


# -------------------------------------------------
# RATING DISTRIBUTION
# -------------------------------------------------
@router.get("/api/ratings/distribution")
async def api_ratings_distribution(company_id: int, start: str | None = None, end: str | None = None):

    async with get_session() as session:

        stmt = (
            select(Review.rating, func.count(Review.id))
            .where(Review.company_id == company_id)
            .group_by(Review.rating)
        )

        if start:
            stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end:
            stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))

        res = await session.execute(stmt)

        dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for rating, count in res.all():
            if rating in dist:
                dist[rating] = count

        return {"distribution": dist}


# -------------------------------------------------
# SENTIMENT TREND
# -------------------------------------------------
@router.get("/api/sentiment/series")
async def api_sentiment_series(company_id: int, start: str | None = None, end: str | None = None):

    async with get_session() as session:

        stmt = (
            select(
                func.date(Review.review_time).label("date"),
                func.avg(Review.sentiment_score).label("value"),
            )
            .where(Review.company_id == company_id)
            .group_by(func.date(Review.review_time))
            .order_by(func.date(Review.review_time))
        )

        if start:
            stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end:
            stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))

        res = await session.execute(stmt)

        return {
            "series": [
                {"date": str(r.date), "value": float(r.value or 0)}
                for r in res.all()
            ]
        }


# -------------------------------------------------
# REVIEWS LIST
# -------------------------------------------------
@router.get("/api/reviews/list")
async def api_reviews_list(
    company_id: int,
    sort: str = "newest",
    start: str | None = None,
    end: str | None = None,
):

    async with get_session() as session:

        stmt = select(Review).where(Review.company_id == company_id)

        if sort == "newest":
            stmt = stmt.order_by(desc(Review.review_time))
        elif sort == "oldest":
            stmt = stmt.order_by(asc(Review.review_time))
        elif sort == "highest":
            stmt = stmt.order_by(desc(Review.rating))
        elif sort == "lowest":
            stmt = stmt.order_by(asc(Review.rating))

        if start:
            stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
        if end:
            stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))

        res = await session.execute(stmt.limit(50))
        items = res.scalars().all()

        return {
            "items": [
                {
                    "author_name": i.author_name,
                    "rating": i.rating,
                    "text": i.text,
                    "review_time": i.review_time.strftime("%Y-%m-%d")
                    if i.review_time
                    else "",
                }
                for i in items
            ]
        }
