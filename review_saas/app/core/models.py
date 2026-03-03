# filename: app/routes/dashboard.py
from __future__ import annotations
import logging
from typing import Dict, Any, List

from fastapi import APIRouter, Request, Query, HTTPException, Body, Depends
from fastapi.responses import HTMLResponse

from starlette.templating import Jinja2Templates

from sqlalchemy import select, func, cast, Date, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.models import Company, Review, User

router = APIRouter(tags=['dashboard'])

templates = Jinja2Templates(directory='app/templates')
logger = logging.getLogger("app.dashboard")


# ────────────────────────────────────────────────
#               HTML DASHBOARD PAGE
# ────────────────────────────────────────────────
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(
    request: Request,
    company_id: int | None = Query(None),
    session: AsyncSession = Depends(get_session)
):
    # Fetch all companies for dropdown
    result = await session.execute(
        select(Company).order_by(Company.name)
    )
    all_companies = result.scalars().all()

    # Determine active company
    active_id = company_id
    if not active_id and all_companies:
        active_id = all_companies[0].id

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "companies": all_companies,
            "active_company_id": active_id
        }
    )


# ────────────────────────────────────────────────
#               API: List all companies
# ────────────────────────────────────────────────
@router.get("/api/companies/list")
async def api_companies_list(session: AsyncSession = Depends(get_session)):
    """
    Returns minimal list of companies (id + name) for frontend dropdown
    """
    result = await session.execute(
        select(Company.id, Company.name).order_by(Company.name)
    )
    companies = [
        {"id": row.id, "name": row.name}
        for row in result.all()
    ]
    return {"companies": companies}


# ────────────────────────────────────────────────
#               API: Add new company from Google Places
# ────────────────────────────────────────────────
@router.post("/companies/add")
async def api_add_company(
    data: Dict[str, Any] = Body(...),
    session: AsyncSession = Depends(get_session)
):
    """
    Saves a new company from Google Places autocomplete data
    Expected fields: name, place_id, address, phone, website, category, hours, google_data
    """
    try:
        # Basic validation
        if not data.get("place_id"):
            raise HTTPException(400, detail="place_id is required")

        # Check for duplicate place_id
        existing = await session.execute(
            select(Company).where(Company.place_id == data["place_id"])
        )
        if existing.scalar_one_or_none():
            raise HTTPException(409, detail="Company with this place_id already exists")

        new_company = Company(
            name=data.get("name"),
            place_id=data["place_id"],
            address=data.get("address"),
            phone=data.get("phone"),
            website=data.get("website"),
            category=data.get("category"),
            hours=data.get("hours"),
            google_data=data.get("google_data"),          # full JSON snapshot
            avg_rating=0.0,
            review_count=0,
            status="active",
            last_updated=None,
            owner_id=None                                 # can be set later if you add auth
        )

        session.add(new_company)
        await session.commit()
        await session.refresh(new_company)

        return {
            "success": True,
            "id": new_company.id,
            "name": new_company.name,
            "message": "Company added successfully"
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception("Failed to add company")
        raise HTTPException(500, detail=f"Server error: {str(e)}")


# ────────────────────────────────────────────────
#               KPI & CHART ENDPOINTS (aligned)
# ────────────────────────────────────────────────

@router.get("/api/kpis")
async def api_kpis(
    company_id: int = Query(...),
    start: str | None = Query(None),
    end: str | None = Query(None),
    session: AsyncSession = Depends(get_session)
):
    q = select(
        func.count(Review.id).label("total_reviews"),
        func.avg(Review.rating).label("avg_rating"),
        func.avg(Review.sentiment_score).label("avg_sentiment")
    ).where(Review.company_id == company_id)

    if start:
        q = q.where(func.date(Review.review_time) >= cast(start, Date))
    if end:
        q = q.where(func.date(Review.review_time) <= cast(end, Date))

    result = await session.execute(q)
    stats = result.fetchone()

    return {
        "total_reviews": int(stats.total_reviews or 0),
        "avg_rating": float(stats.avg_rating or 0.0),
        "avg_sentiment": float(stats.avg_sentiment or 0.0)
    }


@router.get("/api/series/reviews")
async def api_series_reviews(
    company_id: int = Query(...),
    start: str | None = Query(None),
    end: str | None = Query(None),
    session: AsyncSession = Depends(get_session)
):
    stmt = select(
        func.date(Review.review_time).label("date"),
        func.count(Review.id).label("value")
    ).where(Review.company_id == company_id)\
     .group_by(func.date(Review.review_time))\
     .order_by("date")

    if start: stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
    if end:   stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))

    result = await session.execute(stmt)
    return {
        "series": [{"date": str(row.date), "value": int(row.value or 0)} for row in result.all()]
    }


@router.get("/api/ratings/distribution")
async def api_ratings_distribution(
    company_id: int = Query(...),
    start: str | None = Query(None),
    end: str | None = Query(None),
    session: AsyncSession = Depends(get_session)
):
    stmt = select(
        Review.rating,
        func.count(Review.id).label("count")
    ).where(Review.company_id == company_id)\
     .group_by(Review.rating)

    if start: stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
    if end:   stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))

    result = await session.execute(stmt)
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for rating, count in result.all():
        if rating in dist:
            dist[rating] = int(count)

    return {"distribution": dist}


@router.get("/api/sentiment/series")
async def api_sentiment_series(
    company_id: int = Query(...),
    start: str | None = Query(None),
    end: str | None = Query(None),
    session: AsyncSession = Depends(get_session)
):
    stmt = select(
        func.date(Review.review_time).label("date"),
        func.avg(Review.sentiment_score).label("value")
    ).where(Review.company_id == company_id)\
     .group_by(func.date(Review.review_time))\
     .order_by("date")

    if start: stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
    if end:   stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))

    result = await session.execute(stmt)
    return {
        "series": [{"date": str(row.date), "value": float(row.value or 0.0)} for row in result.all()]
    }


@router.get("/api/reviews/list")
async def api_reviews_list(
    company_id: int = Query(...),
    sort: str = Query("newest"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    session: AsyncSession = Depends(get_session)
):
    stmt = select(Review).where(Review.company_id == company_id)

    # Sorting
    if sort == "newest":
        stmt = stmt.order_by(desc(Review.review_time))
    elif sort == "oldest":
        stmt = stmt.order_by(asc(Review.review_time))
    elif sort == "highest":
        stmt = stmt.order_by(desc(Review.rating))
    elif sort == "lowest":
        stmt = stmt.order_by(asc(Review.rating))

    if start: stmt = stmt.where(func.date(Review.review_time) >= cast(start, Date))
    if end:   stmt = stmt.where(func.date(Review.review_time) <= cast(end, Date))

    result = await session.execute(stmt.limit(50))
    reviews = result.scalars().all()

    return {
        "items": [
            {
                "author_name": r.author_name,
                "rating": r.rating,
                "text": r.text,
                "review_time": r.review_time.strftime("%Y-%m-%d") if r.review_time else None
            }
            for r in reviews
        ]
    }
