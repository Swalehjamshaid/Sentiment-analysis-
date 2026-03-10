# filename: app/routes/companies.py
from __future__ import annotations

import logging
import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.templating import Jinja2Templates
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
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.companies")


# ─────────────────────────────────────────
# Auth helper
# ─────────────────────────────────────────
def _require_user(request: Request) -> None:
    if not request.session.get("user"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


# ─────────────────────────────────────────
# Google Maps Client
# ─────────────────────────────────────────
def _get_gmaps_client() -> Optional[Any]:
    key = getattr(settings, "GOOGLE_PLACES_API_KEY", "")
    if not key:
        logger.warning("Google Maps API key not configured")
        return None

    try:
        import googlemaps
        return googlemaps.Client(key=key)
    except Exception as ex:
        logger.warning("Google Maps client failed: %s", ex)
        return None


# ─────────────────────────────────────────
# Google Autocomplete Endpoint
# ─────────────────────────────────────────
@router.get("/google_autocomplete")
async def google_autocomplete(request: Request, input: str = Query(...)):
    _require_user(request)
    client = _get_gmaps_client()
    if not client:
        return JSONResponse(
            status_code=503,
            content={"error": "Google Maps client not configured"}
        )

    try:
        res = await asyncio.to_thread(client.places_autocomplete, input)
        predictions = [{"description": p.get("description"), "place_id": p.get("place_id")} for p in res]
        return {"predictions": predictions}
    except Exception as ex:
        logger.exception("Google autocomplete failed: %s", ex)
        return JSONResponse(
            status_code=500,
            content={"error": "Autocomplete service unavailable"}
        )


# ─────────────────────────────────────────
# Google Place Details
# ─────────────────────────────────────────
@router.get("/google/place/details")
async def google_place_details(request: Request, place_id: str = Query(...)):
    _require_user(request)
    try:
        from app.services.google_places import place_details
        data = await asyncio.to_thread(place_details, place_id)
        result = data.get("result", {})
        return {
            "name": result.get("name"),
            "place_id": result.get("place_id"),
            "address": result.get("formatted_address"),
            "rating": result.get("rating"),
            "user_ratings_total": result.get("user_ratings_total")
        }
    except ImportError:
        raise HTTPException(status_code=503, detail="Google Places service not configured")
    except Exception as ex:
        logger.exception("Google place details failed: %s", ex)
        raise HTTPException(status_code=500, detail="Google place lookup failed")


# ─────────────────────────────────────────
# Companies Data Helper
# ─────────────────────────────────────────
async def _get_companies_data(page: int = 1, size: int = 20, q: Optional[str] = None) -> Dict[str, Any]:
    page = max(1, page)
    size = max(1, min(100, size))
    async with get_session() as session:
        stmt = select(Company)
        if q:
            stmt = stmt.where(Company.name.ilike(f"%{q}%"))
        stmt = stmt.order_by(desc(Company.created_at))

        total_stmt = select(func.count(Company.id))
        if q:
            total_stmt = total_stmt.where(Company.name.ilike(f"%{q}%"))

        total = (await session.execute(total_stmt)).scalar() or 0
        rows = (await session.execute(stmt.offset((page - 1) * size).limit(size))).scalars().all()

        data = []
        for c in rows:
            stats = (await session.execute(
                select(func.count(Review.id), func.avg(Review.rating))
                .where(Review.company_id == c.id)
            )).first()

            data.append({
                "id": int(c.id),
                "name": c.name,
                "place_id": getattr(c, "place_id", ""),
                "address": getattr(c, "address", ""),
                "review_count": int(stats[0] or 0),
                "avg_rating": round(float(stats[1] or 0), 2)
            })

    return {"page": page, "size": size, "total": int(total), "items": data}


# ─────────────────────────────────────────
# Companies List API
# ─────────────────────────────────────────
@router.get("/companies")
async def companies_list(request: Request, page: int = 1, size: int = 20, q: Optional[str] = None):
    _require_user(request)
    data = await _get_companies_data(page, size, q)
    return data


# ─────────────────────────────────────────
# Add Company
# ─────────────────────────────────────────
@router.post("/companies")
async def add_company(
    request: Request,
    background: BackgroundTasks,
    name: str = Form(...),
    place_id: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
):
    _require_user(request)
    async with get_session() as session:
        c = Company(name=name.strip(), place_id=place_id or "", address=address or "")
        session.add(c)
        await session.commit()
        await session.refresh(c)

    client = getattr(request.app.state, "google_reviews_client", None)
    if run_batch_review_ingestion and client:
        background.add_task(run_batch_review_ingestion, client, [c])

    return {
        "status": "ok",
        "company": {"id": int(c.id), "name": c.name, "place_id": c.place_id, "address": c.address}
    }


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
