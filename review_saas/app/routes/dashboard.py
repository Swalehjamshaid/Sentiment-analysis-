
# filename: app/routes/dashboard.py
from __future__ import annotations
from datetime import datetime, timedelta, timezone, date
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import select, func, desc
from app.core.db import get_session
from app.core.models import Company, Review
from app.core.config import settings
from app.core.cache import make_key, get as cache_get, set as cache_set

router = APIRouter(tags=['dashboard'])
templates = Jinja2Templates(directory='app/templates')


def _require_user(request: Request):
    return request.session.get('user_id')

@router.get('/dashboard', response_class=HTMLResponse)
async def dashboard_page(request: Request, company_id: int | None = None):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse('/login', status_code=302)
    async with get_session() as session:
        companies = (await session.execute(select(Company).order_by(Company.created_at.desc()))).scalars().all()
        active_id = company_id or (companies[0].id if companies else None)
    return templates.TemplateResponse('dashboard.html', {"request": request, "companies": companies, "active_company_id": active_id, "title": 'Dashboard'})

@router.get('/api/kpis')
async def api_kpis(company_id: int | None = None, start: str | None = None, end: str | None = None):
    key = make_key('kpis', str(company_id or 0), start or '', end or '')
    c = cache_get(key)
    if c: return c
    if end: end_dt = datetime.fromisoformat(end).date()
    else: end_dt = datetime.now(tz=timezone.utc).date()
    if start: start_dt = datetime.fromisoformat(start).date()
    else: start_dt = end_dt - timedelta(days=29)
    async with get_session() as session:
        q = select(func.count(Review.id), func.avg(Review.rating), func.avg(Review.sentiment_compound))
        q = q.where(Review.review_time != None, func.date(Review.review_time) >= start_dt, func.date(Review.review_time) <= end_dt)
        if company_id: q = q.where(Review.company_id==company_id)
        total, avg_rating, avg_sent = (await session.execute(q)).one()
        # previous period compare
        period = (end_dt - start_dt).days + 1
        prev_start = start_dt - timedelta(days=period)
        prev_end = start_dt - timedelta(days=1)
        qprev = select(func.count(Review.id), func.avg(Review.rating))
        qprev = qprev.where(Review.review_time != None, func.date(Review.review_time) >= prev_start, func.date(Review.review_time) <= prev_end)
        if company_id: qprev = qprev.where(Review.company_id==company_id)
        ptotal, prating = (await session.execute(qprev)).one()
        data = {"total_reviews": int(total or 0), "avg_rating": float(avg_rating or 0.0), "avg_sentiment": float(avg_sent or 0.0), "prev_total": int(ptotal or 0), "prev_avg_rating": float(prating or 0.0)}
    cache_set(key, data)
    return data

@router.get('/api/series/reviews')
async def api_series_reviews(days: int = 30, company_id: int | None = None, start: str | None = None, end: str | None = None):
    if end: end_dt = datetime.fromisoformat(end).date()
    else: end_dt = datetime.now(tz=timezone.utc).date()
    if start: start_dt = datetime.fromisoformat(start).date()
    else: start_dt = end_dt - timedelta(days=days-1)
    async with get_session() as session:
        stmt = select(func.date(Review.review_time), func.count(Review.id))
        stmt = stmt.where(Review.review_time != None, func.date(Review.review_time) >= start_dt, func.date(Review.review_time) <= end_dt)
        if company_id: stmt = stmt.where(Review.company_id==company_id)
        stmt = stmt.group_by(func.date(Review.review_time)).order_by(func.date(Review.review_time))
        rows = (await session.execute(stmt)).all()
        counts = {str(r[0]): int(r[1]) for r in rows if r[0] is not None}
    series = []
    days = (end_dt - start_dt).days + 1
    for i in range(days):
        d = (start_dt + timedelta(days=i)).isoformat()
        series.append({"date": d, "value": counts.get(d, 0)})
    return {"series": series}

@router.get('/api/ratings/distribution')
async def api_ratings_distribution(company_id: int | None = None, start: str | None = None, end: str | None = None):
    if end: end_dt = datetime.fromisoformat(end).date()
    else: end_dt = datetime.now(tz=timezone.utc).date()
    if start: start_dt = datetime.fromisoformat(start).date()
    else: start_dt = end_dt - timedelta(days=29)
    async with get_session() as session:
        dist = {}
        for r in range(1,6):
            stmt = select(func.count(Review.id)).where(Review.rating == r, Review.review_time != None, func.date(Review.review_time) >= start_dt, func.date(Review.review_time) <= end_dt)
            if company_id: stmt = stmt.where(Review.company_id==company_id)
            dist[str(r)] = int((await session.execute(stmt)).scalar() or 0)
    return {"distribution": dist}

@router.get('/api/sentiment/series')
async def api_sentiment_series(company_id: int | None = None, start: str | None = None, end: str | None = None):
    if end: end_dt = datetime.fromisoformat(end).date()
    else: end_dt = datetime.now(tz=timezone.utc).date()
    if start: start_dt = datetime.fromisoformat(start).date()
    else: start_dt = end_dt - timedelta(days=29)
    async with get_session() as session:
        stmt = select(func.date(Review.review_time), func.avg(Review.sentiment_compound)).where(Review.review_time != None, func.date(Review.review_time) >= start_dt, func.date(Review.review_time) <= end_dt)
        if company_id: stmt = stmt.where(Review.company_id==company_id)
        stmt = stmt.group_by(func.date(Review.review_time)).order_by(func.date(Review.review_time))
        rows = (await session.execute(stmt)).all()
        vals = {str(r[0]): float(r[1]) for r in rows if r[0] is not None}
    series = []
    days = (end_dt - start_dt).days + 1
    for i in range(days):
        d = (start_dt + timedelta(days=i)).isoformat()
        series.append({"date": d, "value": vals.get(d, 0.0)})
    return {"series": series}

@router.get('/api/reviews/list')
async def api_reviews_list(company_id: int, start: str | None = None, end: str | None = None, sort: str = 'newest'):
    if end: end_dt = datetime.fromisoformat(end).date()
    else: end_dt = datetime.now(tz=timezone.utc).date()
    if start: start_dt = datetime.fromisoformat(start).date()
    else: start_dt = end_dt - timedelta(days=29)
    async with get_session() as session:
        stmt = select(Review).where(Review.company_id==company_id, Review.review_time != None, func.date(Review.review_time) >= start_dt, func.date(Review.review_time) <= end_dt)
        if sort == 'oldest':
            stmt = stmt.order_by(Review.review_time.asc())
        elif sort == 'highest':
            stmt = stmt.order_by(Review.rating.desc())
        elif sort == 'lowest':
            stmt = stmt.order_by(Review.rating.asc())
        else:
            stmt = stmt.order_by(Review.review_time.desc())
        rows = (await session.execute(stmt)).scalars().all()
        items = [{
            'author_name': r.author_name,
            'review_time': r.review_time.isoformat() if r.review_time else None,
            'rating': r.rating,
            'text': r.text,
            'sentiment_compound': r.sentiment_compound,
        } for r in rows]
    return {"items": items}

@router.get('/api/summary/weekly')
async def api_summary_weekly(company_id: int | None = None):
    end_dt = datetime.now(tz=timezone.utc).date()
    start_dt = end_dt - timedelta(days=6*7)
    async with get_session() as session:
        stmt = select(func.strftime('%Y-%W', Review.review_time), func.count(Review.id), func.avg(Review.rating))
        stmt = stmt.where(Review.review_time != None, func.date(Review.review_time) >= start_dt)
        if company_id: stmt = stmt.where(Review.company_id==company_id)
        stmt = stmt.group_by(func.strftime('%Y-%W', Review.review_time)).order_by(func.strftime('%Y-%W', Review.review_time))
        rows = (await session.execute(stmt)).all()
    return {"weekly": [{"week": k, "count": int(c or 0), "avg_rating": float(a or 0.0)} for k,c,a in rows]}

@router.get('/api/summary/monthly')
async def api_summary_monthly(company_id: int | None = None):
    end_dt = datetime.now(tz=timezone.utc).date()
    start_dt = end_dt - timedelta(days=365)
    async with get_session() as session:
        stmt = select(func.strftime('%Y-%m', Review.review_time), func.count(Review.id), func.avg(Review.rating))
        stmt = stmt.where(Review.review_time != None, func.date(Review.review_time) >= start_dt)
        if company_id: stmt = stmt.where(Review.company_id==company_id)
        stmt = stmt.group_by(func.strftime('%Y-%m', Review.review_time)).order_by(func.strftime('%Y-%m', Review.review_time))
        rows = (await session.execute(stmt)).all()
    return {"monthly": [{"month": k, "count": int(c or 0), "avg_rating": float(a or 0.0)} for k,c,a in rows]}
