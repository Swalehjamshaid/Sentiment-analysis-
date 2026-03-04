# filename: app/routes/dashboard.py
from __future__ import annotations
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy import select, func, desc
from starlette.templating import Jinja2Templates
from app.core.db import get_session
from app.core.models import Company, Review
from app.routes.companies import _require_user
from app.services.google_reviews import ingest_company_reviews

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.dashboard")


@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """
    Renders dashboard and fetches companies from DB and updated reviews.
    """
    uid = _require_user(request)
    if not uid:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)

    async with get_session() as session:
        stmt = (
            select(
                Company.id,
                Company.name,
                Company.address,
                func.count(Review.id).label("review_count"),
                func.coalesce(func.avg(Review.rating), 0).label("avg_rating"),
            )
            .outerjoin(Review, Company.id == Review.company_id)
            .group_by(Company.id, Company.name, Company.address)
            .order_by(desc(Company.created_at))
        )
        res = await session.execute(stmt)
        companies = [
            {
                "id": int(r.id),
                "name": r.name,
                "address": r.address,
                "review_count": int(r.review_count or 0),
                "avg_rating": round(float(r.avg_rating or 0), 2),
            }
            for r in res.all()
        ]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "companies": companies,
        },
    )


@router.get("/api/dashboard/companies")
async def api_dashboard_companies():
    """
    Returns all companies with review_count and avg_rating after any ingestion.
    """
    async with get_session() as session:
        stmt = (
            select(
                Company.id,
                Company.name,
                Company.address,
                func.count(Review.id).label("review_count"),
                func.coalesce(func.avg(Review.rating), 0).label("avg_rating"),
            )
            .outerjoin(Review, Company.id == Review.company_id)
            .group_by(Company.id, Company.name, Company.address)
            .order_by(desc(Company.created_at))
        )
        res = await session.execute(stmt)
        companies = [
            {
                "id": int(r.id),
                "name": r.name,
                "address": r.address,
                "review_count": int(r.review_count or 0),
                "avg_rating": round(float(r.avg_rating or 0), 2),
            }
            for r in res.all()
        ]

    return {"success": True, "results": companies}
