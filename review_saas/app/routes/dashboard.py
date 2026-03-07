# File: app/routes/dashboard.py

from __future__ import annotations
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from collections import Counter

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, desc, cast, Date, and_
from starlette.templating import Jinja2Templates

from app.core.db import get_session
from app.core.models import Review, Company
from app.routes.companies import _require_user

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.dashboard")


def parse_date(date_str: str | None) -> Optional[datetime.date]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None


# ────────────────────────────────────────────────
# Dashboard Page
# ────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    uid = _require_user(request)
    if not uid:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Session expired."}
        )
    return templates.TemplateResponse("dashboard.html", {"request": request})


# ────────────────────────────────────────────────
# KPIs & Ratings
# ────────────────────────────────────────────────

@router.get("/api/kpis")
async def api_kpis(company_id: int, start: str | None = None, end: str | None = None):
    start_dt, end_dt = parse_date(start), parse_date(end)
    async with get_session() as session:
        stmt = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
            func.avg(Review.sentiment_score).label("avg_sent")
        ).where(Review.company_id == company_id)
        if start_dt:
            stmt = stmt.where(cast(Review.google_review_time, Date) >= start_dt)
        if end_dt:
            stmt = stmt.where(cast(Review.google_review_time, Date) <= end_dt)

        res = await session.execute(stmt)
        stats = res.first()
        return {
            "total_reviews": int(stats.total or 0),
            "avg_rating": round(float(stats.avg_rating or 0.0), 2),
            "avg_sentiment": round(float(stats.avg_sent or 0.0), 3)
        }


@router.get("/api/ratings/distribution")
async def api_ratings_distribution(company_id: int, start: str | None = None, end: str | None = None):
    start_dt, end_dt = parse_date(start), parse_date(end)
    async with get_session() as session:
        stmt = select(Review.rating, func.count(Review.id)).where(Review.company_id == company_id)
        if start_dt:
            stmt = stmt.where(cast(Review.google_review_time, Date) >= start_dt)
        if end_dt:
            stmt = stmt.where(cast(Review.google_review_time, Date) <= end_dt)
        stmt = stmt.group_by(Review.rating)
        res = await session.execute(stmt)
        dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for row in res.all():
            dist[int(row[0])] = row[1]
        return {"distribution": dist}


# ────────────────────────────────────────────────
# Reviews & Sentiment Series
# ────────────────────────────────────────────────

@router.get("/api/reviews/list")
async def api_reviews_list(company_id: int, start: str | None = None, end: str | None = None):
    start_dt, end_dt = parse_date(start), parse_date(end)
    async with get_session() as session:
        stmt = select(Review).where(Review.company_id == company_id)
        if start_dt:
            stmt = stmt.where(cast(Review.google_review_time, Date) >= start_dt)
        if end_dt:
            stmt = stmt.where(cast(Review.google_review_time, Date) <= end_dt)
        stmt = stmt.order_by(desc(Review.google_review_time))
        res = await session.execute(stmt)
        items = res.scalars().all()
        return {
            "items": [{
                "author_name": r.author_name or "Anonymous",
                "rating": r.rating,
                "text": r.text or "",
                "sentiment_score": round(r.sentiment_score, 2),
                "review_time": r.google_review_time.strftime("%Y-%m-%d") if r.google_review_time else "",
                "profile_photo_url": r.profile_photo_url or ""
            } for r in items]
        }


@router.get("/api/series/reviews")
async def api_series_reviews(company_id: int, start: str | None = None, end: str | None = None):
    start_dt, end_dt = parse_date(start), parse_date(end)
    async with get_session() as session:
        date_col = cast(Review.google_review_time, Date)
        stmt = select(date_col.label("date"), func.count(Review.id).label("value")).where(Review.company_id == company_id)
        if start_dt: stmt = stmt.where(date_col >= start_dt)
        if end_dt: stmt = stmt.where(date_col <= end_dt)
        stmt = stmt.group_by("date").order_by("date")
        res = await session.execute(stmt)
        return {"series": [{"date": str(r.date), "value": r.value} for r in res.all()]}


@router.get("/api/sentiment/series")
async def api_sentiment_series(company_id: int, start: str | None = None, end: str | None = None):
    start_dt, end_dt = parse_date(start), parse_date(end)
    async with get_session() as session:
        date_col = cast(Review.google_review_time, Date)
        stmt = select(date_col.label("date"), func.avg(Review.sentiment_score).label("value")).where(Review.company_id == company_id)
        if start_dt: stmt = stmt.where(date_col >= start_dt)
        if end_dt: stmt = stmt.where(date_col <= end_dt)
        stmt = stmt.group_by("date").order_by("date")
        res = await session.execute(stmt)
        return {"series": [{"date": str(r.date), "value": round(float(r.value or 0), 3)} for r in res.all()]}


# ────────────────────────────────────────────────
# Executive Verdict & Decision Making
# ────────────────────────────────────────────────

@router.get("/api/owner/executive-summary")
async def api_executive_summary(company_id: int):
    async with get_session() as session:
        # Core KPIs
        stats = await api_kpis(company_id)
        aspects = await api_aspects_average(company_id)

        rating = stats["avg_rating"]
        sentiment = stats["avg_sentiment"]

        # Advanced Decision Logic
        if sentiment < 0.1 and rating > 4.0:
            verdict = "Critical Disconnect: Guests give high stars but express frustration in text. Immediate audit required."
        elif sentiment > 0.4 and rating < 4.0:
            verdict = "Hidden Potential: Guests love experience but penalize price/facilities. Review infrastructure."
        elif rating < 3.5:
            verdict = "Crisis Mode: Brand reputation at risk. Prioritize staff training & negative review response."
        else:
            verdict = "Steady Growth: Maintain current quality. Increase loyalty programs & review volume."

        # Weakest Aspect
        weakest_aspect = min(aspects["aspects"].items(), key=lambda x: x[1] if x[1] is not None else 1.0)

        # Predictive Health Score
        health_score = round(((rating / 5) * 0.5 + (sentiment + 1)/2 * 0.5) * 100, 1)

        return {
            "final_verdict": verdict,
            "top_action_item": f"Address issues in {weakest_aspect[0].upper()} department immediately.",
            "business_health_score": health_score
        }


@router.get("/api/aspects/avg")
async def api_aspects_average(company_id: int, start: str | None = None, end: str | None = None):
    start_dt, end_dt = parse_date(start), parse_date(end)
    async with get_session() as session:
        stmt = select(
            func.avg(Review.aspect_rooms).label("rooms"),
            func.avg(Review.aspect_staff).label("staff"),
            func.avg(Review.aspect_cleanliness).label("cleanliness"),
            func.avg(Review.aspect_value).label("value"),
            func.avg(Review.aspect_location).label("location"),
            func.avg(Review.aspect_food).label("food"),
        ).where(Review.company_id == company_id)
        if start_dt: stmt = stmt.where(cast(Review.google_review_time, Date) >= start_dt)
        if end_dt: stmt = stmt.where(cast(Review.google_review_time, Date) <= end_dt)
        res = await session.execute(stmt)
        row = res.first()
        return {
            "aspects": {
                "rooms": round(float(row.rooms or 0), 3),
                "staff": round(float(row.staff or 0), 3),
                "cleanliness": round(float(row.cleanliness or 0), 3),
                "value": round(float(row.value or 0), 3),
                "location": round(float(row.location or 0), 3),
                "food": round(float(row.food or 0), 3) if row.food is not None else 0.0,
            }
        }


@router.get("/api/complaints/stats")
async def api_complaints_stats(company_id: int, start: str | None = None, end: str | None = None):
    start_dt, end_dt = parse_date(start), parse_date(end)
    async with get_session() as session:
        base = select(Review).where(Review.company_id == company_id)
        if start_dt: base = base.where(cast(Review.google_review_time, Date) >= start_dt)
        if end_dt: base = base.where(cast(Review.google_review_time, Date) <= end_dt)

        res_total = await session.execute(select(func.count()).select_from(base.subquery()))
        total = res_total.scalar() or 0

        res_comp = await session.execute(select(func.count()).select_from(base.subquery()).where(Review.is_complaint == True))
        complaints = res_comp.scalar() or 0

        res_praise = await session.execute(select(func.count()).select_from(base.subquery()).where(Review.is_praise == True))
        praise = res_praise.scalar() or 0

        complaint_rate = round(complaints / total * 100, 1) if total > 0 else 0.0

        return {
            "total_reviews": total,
            "complaint_count": complaints,
            "complaint_rate": complaint_rate,
            "praise_count": praise
        }


@router.get("/api/keywords/top")
async def api_top_keywords(company_id: int, start: str | None = None, end: str | None = None, limit: int = Query(12, ge=5, le=30)):
    start_dt, end_dt = parse_date(start), parse_date(end)
    async with get_session() as session:
        stmt = select(Review.text).where(Review.company_id == company_id)
        if start_dt: stmt = stmt.where(cast(Review.google_review_time, Date) >= start_dt)
        if end_dt: stmt = stmt.where(cast(Review.google_review_time, Date) <= end_dt)
        res = await session.execute(stmt)
        texts = [r[0] or "" for r in res.all() if r[0]]
        if not texts:
            return {"positive_keywords": [], "negative_keywords": []}

        # Clean & tokenize
        words = []
        for text in texts:
            cleaned = re.sub(r'[^a-zA-Z\s]', '', text.lower())
            words.extend(cleaned.split())

        common = Counter(words).most_common(limit * 3)
        stop = {'the', 'and', 'to', 'a', 'i', 'in', 'is', 'it', 'of', 'for', 'on', 'was', 'with', 'at', 'this'}
        filtered = [(w, c) for w, c in common if w not in stop and len(w) > 3]

        pos_indicators = {'great', 'excellent', 'good', 'friendly', 'clean', 'amazing', 'love', 'nice', 'comfortable'}
        neg_indicators = {'bad', 'poor', 'worst', 'slow', 'dirty', 'rude', 'problem', 'issue', 'disappointed'}

        return {
            "positive_keywords": [w for w, _ in filtered if w in pos_indicators][:limit],
            "negative_keywords": [w for w, _ in filtered if w in neg_indicators][:limit]
        }
