# filename: app/routes/companies.py

from __future__ import annotations

import json
import logging
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, Query, Request, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import desc, func, select

from app.core.db import get_session
from app.core.models import Company, Review
from app.core.config import settings

# Optional Review ingestion
try:
    from app.services.google_reviews import run_batch_review_ingestion
except Exception:
    run_batch_review_ingestion = None

router = APIRouter(tags=["companies"], prefix="/api")
logger = logging.getLogger("app.companies")


# ─────────────────────────────────────────
# JSON Schema for Adding Company
# ─────────────────────────────────────────
class CompanyCreate(BaseModel):
    name: str
    place_id: str
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    categories: Optional[List[str]] = None


# ─────────────────────────────────────────
# Auth helper
# ─────────────────────────────────────────
def _require_user(request: Request) -> None:
    if not request.session.get("user"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized"
        )


# ─────────────────────────────────────────
# Companies List API (with Outscaper fields)
# ─────────────────────────────────────────
@router.get("/companies")
async def companies_list(request: Request, page: int = 1, size: int = 20, q: Optional[str] = None):
    _require_user(request)
    page = max(1, page)
    size = max(1, min(100, size))
    async with get_session() as session:
        stmt = select(Company)
        if q:
            stmt = stmt.where(Company.name.ilike(f"%{q}%"))
        stmt = stmt.order_by(desc(Company.created_at))
        rows = (await session.execute(stmt.offset((page - 1) * size).limit(size))).scalars().all()

        data = []
        for c in rows:
            stats = (await session.execute(
                select(func.count(Review.id), func.avg(Review.rating)).where(Review.company_id == c.id)
            )).first()
            data.append({
                "id": int(c.id),
                "name": c.name,
                "place_id": getattr(c, "place_id", ""),
                "address": getattr(c, "address", ""),
                "lat": getattr(c, "lat", None),
                "lng": getattr(c, "lng", None),
                "phone": getattr(c, "phone", ""),
                "website": getattr(c, "website", ""),
                "categories": getattr(c, "categories", []),
                "review_count": int(stats[0] or 0),
                "avg_rating": round(float(stats[1] or 0), 2),
            })
        return data


# ─────────────────────────────────────────
# Add Company (with Outscaper integration)
# ─────────────────────────────────────────
@router.post("/companies")
async def add_company(request: Request, background: BackgroundTasks, company_in: CompanyCreate):
    _require_user(request)
    async with get_session() as session:
        existing = await session.execute(select(Company).where(Company.place_id == company_in.place_id))
        existing_company = existing.scalar_one_or_none()
        if existing_company:
            # Existing company: fetch incremental reviews from last review
            client = getattr(request.app.state, "reviews_client", None)
            if run_batch_review_ingestion and client:
                latest_review = await session.execute(
                    select(Review).where(Review.company_id == existing_company.id).order_by(desc(Review.google_review_time))
                )
                last_review = latest_review.scalars().first()
                start_date = last_review.google_review_time if last_review else datetime(2000, 1, 1)
                end_date = datetime.utcnow()
                background.add_task(
                    run_batch_review_ingestion, client, [existing_company], session=session, start=start_date, end=end_date
                )
            return {"status": "exists", "company": {
                "id": int(existing_company.id),
                "name": existing_company.name,
                "place_id": existing_company.place_id,
                "address": existing_company.address,
                "lat": existing_company.lat,
                "lng": existing_company.lng,
                "phone": existing_company.phone,
                "website": existing_company.website,
                "categories": existing_company.categories or [],
            }}

        # New company: save full Outscaper data
        c = Company(
            name=company_in.name.strip(),
            place_id=company_in.place_id.strip(),
            address=company_in.address or "",
            lat=company_in.lat,
            lng=company_in.lng,
            phone=company_in.phone,
            website=company_in.website,
            categories=company_in.categories or [],
        )
        session.add(c)
        await session.commit()
        await session.refresh(c)

        client = getattr(request.app.state, "reviews_client", None)
        if run_batch_review_ingestion and client:
            start_date = datetime(2000, 1, 1)
            end_date = datetime.utcnow()
            background.add_task(run_batch_review_ingestion, client, [c], session=session, start=start_date, end=end_date)

    return {"status": "ok", "company": {
        "id": int(c.id),
        "name": c.name,
        "place_id": c.place_id,
        "address": c.address,
        "lat": c.lat,
        "lng": c.lng,
        "phone": c.phone,
        "website": c.website,
        "categories": c.categories,
    }}


# ─────────────────────────────────────────
# Delete Company
# ─────────────────────────────────────────
@router.post("/companies/{company_id}/delete")
async def delete_company(request: Request, company_id: int):
    _require_user(request)
    async with get_session() as session:
        comp = await session.get(Company, company_id)
        if not comp:
            raise HTTPException(status_code=404, detail="Company not found")
        await session.delete(comp)
        await session.commit()
    return RedirectResponse(url="/dashboard", status_code=302)
