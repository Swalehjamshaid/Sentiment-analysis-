# filename: app/routes/companies.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import desc, func, select

from app.core.db import get_session
from app.core.models import Company, Review

# Optional AuditLog model
try:
    from app.core.models import AuditLog  # type: ignore
except Exception:  # pragma: no cover
    AuditLog = None  # type: ignore

# Optional settings
try:
    from app.core.config import settings  # type: ignore
except Exception:  # pragma: no cover
    class _S:
        google_maps_api_key: str = ""
    settings = _S()  # type: ignore

# Google places service
try:
    from app.services.google_places import place_details, client as google_places_client  # type: ignore
except Exception:
    place_details = None
    google_places_client = None

# Review ingestion
try:
    from app.services.google_reviews import run_batch_review_ingestion  # type: ignore
except Exception:  # pragma: no cover
    run_batch_review_ingestion = None  # type: ignore


router = APIRouter(tags=["companies"], prefix="/api")
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.companies")


# ─────────────────────────────────────────────────────────
# Auth helper
# ─────────────────────────────────────────────────────────
def _require_user(request: Request) -> None:
    if not request.session.get("user"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


# ─────────────────────────────────────────────────────────
# Google Maps Client
# ─────────────────────────────────────────────────────────
def _get_gmaps_client() -> Optional[Any]:
    key = getattr(settings, "google_maps_api_key", "")
    if not key:
        return None
    try:
        import googlemaps
        return googlemaps.Client(key=key)
    except Exception as ex:
        logger.info("googlemaps not available: %s", ex)
        return None


# ─────────────────────────────────────────────────────────
# NEW: Backend Google Autofetch Endpoint
# ─────────────────────────────────────────────────────────
@router.get("/google/place/details")
async def google_place_details(request: Request, place_id: str = Query(...)):
    """
    Fetch Google place details via backend.
    Used for auto-filling company form.
    """
    _require_user(request)

    if not place_details:
        raise HTTPException(status_code=503, detail="Google Places service not configured")

    try:
        data = place_details(place_id)
        result = data.get("result", {})

        return {
            "name": result.get("name"),
            "place_id": result.get("place_id"),
            "address": result.get("formatted_address"),
            "rating": result.get("rating"),
            "user_ratings_total": result.get("user_ratings_total")
        }

    except Exception as ex:
        logger.exception("Google place details failed: %s", ex)
        raise HTTPException(status_code=500, detail="Google place lookup failed")


# ─────────────────────────────────────────────────────────
# Existing data aggregators
# ─────────────────────────────────────────────────────────
async def _get_companies_data(page: int = 1, size: int = 20, q: Optional[str] = None) -> Dict[str, Any]:
    page = max(1, page)
    size = max(1, min(100, size))

    async with get_session() as session:
        stmt = select(Company)

        if q:
            like = f"%{q}%"
            try:
                stmt = stmt.where(Company.name.ilike(like))
            except Exception:
                stmt = stmt.where(Company.name.like(like))

        stmt = stmt.order_by(desc(getattr(Company, "created_at", Company.id)))

        total = (await session.execute(select(func.count(Company.id)).select_from(Company))).scalar() or 0
        rows = (await session.execute(stmt.offset((page - 1) * size).limit(size))).scalars().all() or []

        data: List[Dict[str, Any]] = []

        for c in rows:
            stats = (
                await session.execute(
                    select(func.count(Review.id), func.avg(Review.rating)).where(Review.company_id == c.id)
                )
            ).first()

            data.append(
                {
                    "id": int(c.id),
                    "name": getattr(c, "name", ""),
                    "place_id": getattr(c, "place_id", ""),
                    "address": getattr(c, "address", ""),
                    "review_count": int(stats[0] or 0) if stats else 0,
                    "avg_rating": round(float(stats[1] or 0.0), 2) if stats else 0.0,
                }
            )

    return {"page": page, "size": size, "total": int(total), "items": data}


# ─────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────
@router.get("/companies", response_class=HTMLResponse)
async def companies_page(request: Request, page: int = 1, size: int = 20, q: Optional[str] = None):
    _require_user(request)
    payload = await _get_companies_data(page=page, size=size, q=q)

    try:
        return templates.TemplateResponse("companies.html", {"request": request, **payload})
    except Exception:
        items = ''.join(
            [
                f"<li>#{i['id']} {i['name']} — Reviews: {i['review_count']} (avg {i['avg_rating']})</li>"
                for i in payload["items"]
            ]
        )
        html = f"<h2>Companies</h2><ul>{items}</ul>"
        return HTMLResponse(html)


# ─────────────────────────────────────────────────────────
# API list
# ─────────────────────────────────────────────────────────
@router.get("/companies/list")
async def companies_list(request: Request, page: int = 1, size: int = 20, q: Optional[str] = None):
    _require_user(request)
    return await _get_companies_data(page=page, size=size, q=q)


# ─────────────────────────────────────────────────────────
# Google Search
# ─────────────────────────────────────────────────────────
@router.get("/google/places/search")
async def google_places_search(request: Request, q: str = Query(..., min_length=3)):
    _require_user(request)

    client = _get_gmaps_client()
    if not client:
        raise HTTPException(status_code=503, detail="Google Maps client not configured")

    try:
        res = client.places(q)

        out = []

        for r in res.get("results", []):
            out.append(
                {
                    "place_id": r.get("place_id"),
                    "name": r.get("name"),
                    "formatted_address": r.get("formatted_address")
                    or (r.get("vicinity") or ""),
                }
            )

        return {"items": out}

    except Exception as ex:
        logger.exception("Google Places search failed: %s", ex)
        raise HTTPException(status_code=500, detail="Google Places search failed")


# ─────────────────────────────────────────────────────────
# Add Company
# ─────────────────────────────────────────────────────────
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

        if place_id:
            existing = (
                await session.execute(select(Company).where(Company.place_id == place_id))
            ).scalars().first()

            if existing:
                raise HTTPException(status_code=400, detail="Company already exists for this place_id")

        c = Company(name=name.strip(), place_id=place_id or "", address=address or "")
        session.add(c)

        await session.commit()
        await session.refresh(c)

        try:
            if AuditLog is not None:
                log = AuditLog(
                    action="company_add",
                    entity_id=c.id,
                    meta={"name": name, "place_id": place_id or ""},
                )
                session.add(log)
                await session.commit()
        except Exception:
            pass

    client = getattr(request.app.state, "reviews_client", None)

    if run_batch_review_ingestion and client:
        background.add_task(run_batch_review_ingestion, client, [c])

    payload = await _get_companies_data(page=1, size=20, q=None)

    return {
        "status": "ok",
        "company": {
            "id": int(c.id),
            "name": c.name,
            "place_id": c.place_id,
            "address": c.address,
        },
        "list": payload,
    }


# ─────────────────────────────────────────────────────────
# Sync Reviews
# ─────────────────────────────────────────────────────────
@router.post("/companies/{company_id}/sync")
async def sync_company_reviews(request: Request, background: BackgroundTasks, company_id: int):
    _require_user(request)

    async with get_session() as session:
        comp = await session.get(Company, company_id)

        if not comp:
            raise HTTPException(status_code=404, detail="Company not found")

    client = getattr(request.app.state, "reviews_client", None)

    if not (run_batch_review_ingestion and client):
        raise HTTPException(status_code=503, detail="Reviews client or ingestion unavailable")

    background.add_task(run_batch_review_ingestion, client, [comp])

    return {"status": "queued", "company_id": company_id}


# ─────────────────────────────────────────────────────────
# Delete Company
# ─────────────────────────────────────────────────────────
@router.post("/companies/{company_id}/delete")
async def delete_company(request: Request, company_id: int):
    _require_user(request)

    async with get_session() as session:

        comp = await session.get(Company, company_id)

        if not comp:
            raise HTTPException(status_code=404, detail="Company not found")

        try:
            if AuditLog is not None:
                log = AuditLog(
                    action="company_delete",
                    entity_id=comp.id,
                    meta={"name": comp.name},
                )
                session.add(log)
        except Exception:
            pass

        await session.delete(comp)
        await session.commit()

    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
