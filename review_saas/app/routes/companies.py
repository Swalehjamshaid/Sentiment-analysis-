# filename: app/routes/companies.py

from __future__ import annotations

import logging
import asyncio
import httpx
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, Query, Request, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import desc, func, select

from app.core.db import get_session
from app.core.models import Company, Review
from app.core.config import settings

# Outscraper Service Integration
try:
    from app.services.review import sync_all_companies_with_outscaper, update_company_from_outscaper
except ImportError:
    sync_all_companies_with_outscaper = None
    update_company_from_outscaper = None

router = APIRouter(tags=["companies"], prefix="/api")
logger = logging.getLogger("app.companies")


# ─────────────────────────────────────────
# JSON Schema for Adding Company
# ─────────────────────────────────────────
class CompanyCreate(BaseModel):
    name: str
    place_id: str
    address: Optional[str] = None


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
# Outscraper REST client
# ─────────────────────────────────────────
class OutscraperClient:
    BASE_URL = "https://api.app.outscraper.com/maps"

    def __init__(self, api_key: str):
        if not api_key:
            raise RuntimeError("Outscraper API key is missing")
        self.api_key = api_key
        self.headers = {"X-API-KEY": self.api_key}

    async def search_business(self, query: str) -> List[Dict[str, Any]]:
        params = {
            "query": query,
            "limit": 5,
            "async": "false"
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/search-v2",
                    params=params,
                    headers=self.headers
                )

                resp.raise_for_status()
                data = resp.json()
                return data.get("data", [])

            except Exception as e:
                logger.error(f"Outscraper search failed: {e}")
                return []

    async def get_details(self, place_id: str) -> Dict[str, Any]:

        params = {
            "query": place_id,
            "limit": 1,
            "async": "false"
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/search-v2",
                    params=params,
                    headers=self.headers
                )

                resp.raise_for_status()

                results = resp.json().get("data", [])

                return results[0] if results else {}

            except Exception as e:
                logger.error(f"Outscraper details lookup failed: {e}")
                return {}


def _get_outscraper_client() -> Optional[OutscraperClient]:

    key = os.getenv("OUTSCRAPER_API_KEY") or getattr(settings, "OUTSCRAPER_API_KEY", None)

    if not key:
        logger.warning("Outscraper API key not configured")
        return None

    return OutscraperClient(api_key=key)


# ─────────────────────────────────────────
# Search Endpoint
# ─────────────────────────────────────────
@router.get("/google_autocomplete")
async def google_autocomplete(
    request: Request,
    input: str = Query(..., min_length=1, max_length=120)
):

    _require_user(request)

    client = _get_outscraper_client()

    if not client:
        return JSONResponse(
            status_code=503,
            content={"error": "Search client not configured"}
        )

    try:
        res = await client.search_business(input)

        predictions = [
            {
                "description": f"{p.get('name')} - {p.get('full_address')}",
                "place_id": p.get("place_id")
            }
            for p in res
        ]

        return {"predictions": predictions}

    except Exception as ex:

        logger.exception("Autocomplete failed: %s", ex)

        return JSONResponse(
            status_code=502,
            content={"error": "Search service error"}
        )


# ─────────────────────────────────────────
# Details Endpoint
# ─────────────────────────────────────────
@router.get("/google/place/details")
async def google_place_details(
    request: Request,
    place_id: str = Query(..., min_length=5)
):

    _require_user(request)

    client = _get_outscraper_client()

    if not client:
        raise HTTPException(
            status_code=503,
            detail="Search client not configured"
        )

    try:

        data = await client.get_details(place_id)

        if not data:
            raise HTTPException(
                status_code=404,
                detail="Business not found"
            )

        return {
            "name": data.get("name"),
            "place_id": data.get("place_id"),
            "address": data.get("full_address"),
            "rating": data.get("rating"),
            "user_ratings_total": data.get("reviews_count"),
            "website": data.get("site"),
            "url": data.get("google_maps_url"),
            "location": {
                "lat": data.get("latitude"),
                "lng": data.get("longitude")
            }
        }

    except Exception as ex:

        logger.exception("Place details lookup failed: %s", ex)

        raise HTTPException(
            status_code=502,
            detail="Business details lookup failed"
        )


# ─────────────────────────────────────────
# Companies List API
# ─────────────────────────────────────────
@router.get("/companies")
async def companies_list(
    request: Request,
    page: int = 1,
    size: int = 20,
    q: Optional[str] = None
):

    _require_user(request)

    page = max(1, page)
    size = max(1, min(100, size))

    async for session in get_session():

        stmt = select(Company)

        if q:
            stmt = stmt.where(
                Company.name.ilike(f"%{q}%")
            )

        stmt = stmt.order_by(desc(Company.created_at))

        result = await session.execute(
            stmt.offset((page - 1) * size).limit(size)
        )

        rows = result.scalars().all()

        data = []

        for c in rows:

            stats_stmt = select(
                func.count(Review.id),
                func.avg(Review.rating)
            ).where(
                Review.company_id == c.id
            )

            stats_res = await session.execute(stats_stmt)

            stats = stats_res.first()

            data.append({
                "id": int(c.id),
                "name": c.name,
                "place_id": getattr(c, "place_id", getattr(c, "google_place_id", "")),
                "address": c.address or "",
                "review_count": int(stats[0] or 0),
                "avg_rating": round(float(stats[1] or 0), 2),
            })

        return data


# ─────────────────────────────────────────
# Add Company
# ─────────────────────────────────────────
@router.post("/companies")
async def add_company(
    request: Request,
    background: BackgroundTasks,
    company_in: CompanyCreate
):

    _require_user(request)

    async for session in get_session():

        stmt = select(Company).where(
            (Company.place_id == company_in.place_id)
        )

        existing = await session.execute(stmt)

        existing_company = existing.scalar_one_or_none()

        if existing_company:

            if update_company_from_outscaper:
                background.add_task(
                    update_company_from_outscaper,
                    existing_company,
                    session
                )

            return {
                "status": "exists",
                "company": {
                    "id": int(existing_company.id),
                    "name": existing_company.name,
                    "place_id": company_in.place_id,
                    "address": existing_company.address,
                }
            }

        new_comp = Company(
            name=company_in.name.strip(),
            place_id=company_in.place_id.strip(),
            address=company_in.address or "",
            is_active=True
        )

        session.add(new_comp)

        await session.commit()

        await session.refresh(new_comp)

        if update_company_from_outscaper:
            background.add_task(
                update_company_from_outscaper,
                new_comp,
                session
            )

        return {
            "status": "ok",
            "company": {
                "id": int(new_comp.id),
                "name": new_comp.name,
                "place_id": new_comp.place_id,
                "address": new_comp.address,
            }
        }


# ─────────────────────────────────────────
# Delete Company
# ─────────────────────────────────────────
@router.post("/companies/{company_id}/delete")
async def delete_company(
    request: Request,
    company_id: int
):

    _require_user(request)

    async for session in get_session():

        comp = await session.get(Company, company_id)

        if not comp:
            raise HTTPException(
                status_code=404,
                detail="Company not found"
            )

        await session.delete(comp)

        await session.commit()

    return RedirectResponse(
        url="/dashboard",
        status_code=302
    )
