# filename: app/routes/companies.py

from __future__ import annotations

import logging
import httpx
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Request,
    HTTPException,
    status,
    BackgroundTasks,
    Query,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.models import Company, Review
from app.core.config import settings

logger = logging.getLogger("app.companies")

router = APIRouter(tags=["companies"], prefix="/api")


# ----------------------------------------------------------
# AUTH CHECK
# ----------------------------------------------------------

def _require_user(request: Request):
    if not request.session.get("user"):
        raise HTTPException(401, "Unauthorized")


# ----------------------------------------------------------
# PAYLOAD
# ----------------------------------------------------------

class CompanyCreate(BaseModel):
    name: str
    place_id: str
    address: Optional[str] = None


# ----------------------------------------------------------
# OUTSCRAPER CLIENT
# ----------------------------------------------------------

class OutscraperClient:
    BASE = "https://api.app.outscraper.com/maps"

    def __init__(self, api_key: str):
        if not api_key:
            raise RuntimeError("Outscraper API key missing")
        self.api_key = api_key

    async def search(self, query: str):
        params = {"query": query, "async": "false", "limit": 5}
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"{self.BASE}/search-v2", params=params, headers={"X-API-KEY": self.api_key})
            r.raise_for_status()
            return r.json().get("data", [])

    async def details(self, place_id: str):
        params = {"query": place_id, "async": "false", "limit": 1}
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"{self.BASE}/details", params=params, headers={"X-API-KEY": self.api_key})
            r.raise_for_status()
            data = r.json().get("data", [])
            return data[0] if data else None


def _osc():
    key = os.getenv("OUTSCRAPER_API_KEY") or settings.OUTSCRAPER_API_KEY
    if not key:
        return None
    return OutscraperClient(key)


# ----------------------------------------------------------
# COMPANIES LIST
# ----------------------------------------------------------

@router.get("/companies")
async def companies_list(
    request: Request,
    page: int = 1,
    size: int = 20,
    q: Optional[str] = None
):
    _require_user(request)

    page = max(page, 1)
    size = max(1, min(100, size))

    async for session in get_session():
        stmt = select(Company)

        if q:
            stmt = stmt.where(Company.name.ilike(f"%{q}%"))

        stmt = stmt.order_by(desc(Company.created_at))

        res = await session.execute(stmt.offset((page - 1) * size).limit(size))
        companies = res.scalars().all()

        items = []

        for c in companies:
            stats = await session.execute(
                select(func.count(Review.id), func.avg(Review.rating)).where(Review.company_id == c.id)
            )
            count, avg = stats.first()

            items.append({
                "id": c.id,
                "name": c.name,
                "place_id": c.google_place_id,
                "address": c.address or "",
                "review_count": int(count or 0),
                "avg_rating": round(float(avg or 0), 2),
            })

        return items


# ----------------------------------------------------------
# ADD COMPANY (CORRECTED)
# ----------------------------------------------------------

@router.post("/companies")
async def add_company(
    request: Request,
    company_in: CompanyCreate,
    background: BackgroundTasks
):
    _require_user(request)

    async for session in get_session():

        # FIXED — model uses google_place_id, NOT place_id
        res = await session.execute(
            select(Company).where(Company.google_place_id == company_in.place_id)
        )
        existing = res.scalar_one_or_none()

        if existing:
            return {
                "status": "exists",
                "company": {
                    "id": existing.id,
                    "name": existing.name,
                    "place_id": existing.google_place_id,
                    "address": existing.address,
                }
            }

        new_company = Company(
            name=company_in.name.strip(),
            google_place_id=company_in.place_id.strip(),
            address=company_in.address or "",
        )

        session.add(new_company)
        await session.commit()
        await session.refresh(new_company)

        return {
            "status": "created",
            "company": {
                "id": new_company.id,
                "name": new_company.name,
                "place_id": new_company.google_place_id,
                "address": new_company.address,
            }
        }


# ----------------------------------------------------------
# DELETE COMPANY
# ----------------------------------------------------------

@router.post("/companies/{company_id}/delete")
async def delete_company(request: Request, company_id: int):
    _require_user(request)

    async for session in get_session():
        comp = await session.get(Company, company_id)

        if not comp:
            raise HTTPException(404, "Company not found")

        await session.delete(comp)
        await session.commit()

    return {"status": "deleted", "id": company_id}
