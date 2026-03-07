from __future__ import annotations
import logging
import googlemaps
from fastapi import APIRouter, Request, BackgroundTasks, Query, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import select, delete, or_, func, desc
from pydantic import BaseModel

from app.core.db import get_session
from app.core.models import Company, AuditLog, User, Review
from app.core.config import settings
from app.services.google_reviews import ingest_company_reviews

logger = logging.getLogger(__name__)

# Fixed: Added prefix="/api" to match frontend calls seen in logs
router = APIRouter(prefix="/api", tags=["companies"])
templates = Jinja2Templates(directory="app/templates")

# ---------------------------------------------------------
# Helper: Authentication
# ---------------------------------------------------------
def _require_user(request: Request):
    return request.session.get("user_id")

# ---------------------------------------------------------
# Safe Google Maps Client Initializer
# ---------------------------------------------------------
def _get_gmaps_client():
    if not settings.GOOGLE_PLACES_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Google Places API key is not configured."
        )
    return googlemaps.Client(key=settings.GOOGLE_PLACES_API_KEY)

# ---------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------
class PlaceSearchResult(BaseModel):
    place_id: str
    name: str
    formatted_address: str | None = None

class AddCompanyRequest(BaseModel):
    name: str
    place_id: str
    address: str | None = None

# ---------------------------------------------------------
# Helper: Fetch Companies With Aggregated Data
# ---------------------------------------------------------
async def _get_companies_data(session, uid: int):
    stmt = (
        select(
            Company.id,
            Company.name,
            Company.address,
            Company.google_place_id,
            func.count(Review.id).label("review_count"),
            func.coalesce(func.avg(Review.rating), 0).label("avg_rating"),
        )
        .outerjoin(Review, Company.id == Review.company_id)
        .where(Company.owner_id == uid)
        .group_by(Company.id, Company.name, Company.address, Company.google_place_id)
        .order_by(desc(Company.created_at))
    )

    res = await session.execute(stmt)

    return [
        {
            "id": int(r.id),
            "name": r.name,
            "address": r.address or "",
            "place_id": r.google_place_id or "",
            "review_count": int(r.review_count or 0),
            "avg_rating": round(float(r.avg_rating or 0), 2),
        }
        for r in res.all()
    ]

# ---------------------------------------------------------
# UI Route: Companies Page (Adjusted to override /api prefix)
# ---------------------------------------------------------
@router.get("/companies", response_class=HTMLResponse, include_in_schema=False)
async def companies_page(request: Request, q: str | None = None, page: int = 1, size: int = 10):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse("/login", status_code=302)

    async with get_session() as session:
        user_check = await session.execute(select(User).where(User.id == uid))
        if not user_check.scalar_one_or_none():
            request.session.clear()
            return RedirectResponse("/login", status_code=302)

        stmt = select(Company).where(Company.owner_id == uid).order_by(Company.created_at.desc())

        if q:
            stmt = stmt.where(
                or_(
                    Company.name.ilike(f"%{q}%"),
                    Company.address.ilike(f"%{q}%")
                )
            )

        result = await session.execute(stmt)
        all_rows = result.scalars().all()

        total = len(all_rows)
        items = all_rows[(page - 1) * size : (page - 1) * size + size]

    return templates.TemplateResponse(
        "companies.html",
        {
            "request": request,
            "items": items,
            "page": page,
            "size": size,
            "total": total,
            "q": q or "",
        },
    )

# ---------------------------------------------------------
# API: List Companies (Full Path: /api/companies/list)
# ---------------------------------------------------------
@router.get("/companies/list")
async def list_companies(request: Request):
    uid = _require_user(request)
    if not uid:
        return JSONResponse({"success": False, "companies": []}, status_code=401)

    async with get_session() as session:
        data = await _get_companies_data(session, uid)

    return {"success": True, "companies": data}

# ---------------------------------------------------------
# API: Search Google Places (Full Path: /api/google/places/search)
# ---------------------------------------------------------
@router.get("/google/places/search")
async def search_google_places(q: str = Query(..., min_length=3)):
    try:
        gmaps_client = _get_gmaps_client()
        result = gmaps_client.places(query=q)

        places = [
            PlaceSearchResult(
                place_id=p["place_id"],
                name=p["name"],
                formatted_address=p.get("formatted_address"),
            )
            for p in result.get("results", [])
        ]
        return {"success": True, "results": places}
    except Exception as e:
        logger.error(f"Google search error: {e}")
        return {"success": False, "message": str(e)}

# ---------------------------------------------------------
# API: Add New Company (Full Path: /api/companies/add)
# ---------------------------------------------------------
@router.post("/companies/add")
async def add_new_company(request: Request, data: AddCompanyRequest, bg_tasks: BackgroundTasks):
    uid = _require_user(request)
    if not uid:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)

    async with get_session() as session:
        existing = await session.execute(
            select(Company).where(
                Company.google_place_id == data.place_id,
                Company.owner_id == uid,
            )
        )

        if existing.scalar_one_or_none():
            return JSONResponse(
                {"success": False, "message": "Company already exists"},
                status_code=400,
            )

        new_company = Company(
            name=data.name,
            google_place_id=data.place_id,
            address=data.address,
            owner_id=uid,
        )

        session.add(new_company)
        await session.flush()

        session.add(
            AuditLog(
                user_id=uid,
                action="company_add_google",
                meta={"company_id": new_company.id},
            )
        )

        await session.commit()
        await session.refresh(new_company)

        bg_tasks.add_task(
            ingest_company_reviews,
            new_company.google_place_id,
            new_company.id,
        )

        companies = await _get_companies_data(session, uid)

    return {
        "success": True,
        "company": {"id": new_company.id, "name": new_company.name},
        "companies": companies,
        "message": "Company saved! Review sync started.",
    }

# ---------------------------------------------------------
# API: Sync Company Reviews (Full Path: /api/companies/{id}/sync)
# ---------------------------------------------------------
@router.post("/companies/{company_id}/sync")
async def company_sync(company_id: int, request: Request, bg_tasks: BackgroundTasks):
    uid = _require_user(request)
    if not uid:
        return JSONResponse({"success": False}, status_code=401)

    async with get_session() as session:
        result = await session.execute(
            select(Company).where(
                Company.id == company_id,
                Company.owner_id == uid,
            )
        )

        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        bg_tasks.add_task(
            ingest_company_reviews,
            company.google_place_id,
            company.id,
        )

        session.add(
            AuditLog(
                user_id=uid,
                action="company_sync_triggered",
                meta={"company_id": company.id},
            )
        )

        await session.commit()
        companies = await _get_companies_data(session, uid)

    return {
        "success": True,
        "message": "Review sync started!",
        "companies": companies,
    }

# ---------------------------------------------------------
# POST: Delete Company (Full Path: /api/companies/{id}/delete)
# ---------------------------------------------------------
@router.post("/companies/{company_id}/delete")
async def company_delete(request: Request, company_id: int):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse("/login", status_code=302)

    async with get_session() as session:
        await session.execute(
            delete(Company).where(
                Company.id == company_id,
                Company.owner_id == uid,
            )
        )

        session.add(
            AuditLog(
                user_id=uid,
                action="company_delete",
                meta={"company_id": company_id},
            )
        )

        await session.commit()

    return RedirectResponse("/companies", status_code=302)
