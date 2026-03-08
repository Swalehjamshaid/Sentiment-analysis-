from __future__ import annotations
import logging
import googlemaps
from fastapi import APIRouter, Request, BackgroundTasks, Query, HTTPException, Depends
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import select, delete, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.db import get_session
from app.core.models import Company, AuditLog, User, Review
from app.core.config import settings
from app.services.google_reviews import ingest_company_reviews

logger = logging.getLogger(__name__)

# Prefix matches the frontend calls /api/...
router = APIRouter(prefix="/api", tags=["companies"])
templates = Jinja2Templates(directory="app/templates")

# ---------------------------------------------------------
# Helper: Authentication & API Client
# ---------------------------------------------------------
def _require_user(request: Request):
    return request.session.get("user_id")

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
    google_place_id: str  # Matches 'google_place_id' from dashboard.html
    address: str | None = None

# ---------------------------------------------------------
# UI Route: Companies Management Page
# ---------------------------------------------------------
@router.get("/companies", response_class=HTMLResponse, include_in_schema=False)
async def companies_page(request: Request, q: str | None = None, page: int = 1, size: int = 10):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse("/login", status_code=302)

    async with get_session() as session:
        # Paging and Filtering logic
        stmt = select(Company).where(Company.owner_id == uid).order_by(Company.created_at.desc())
        if q:
            stmt = stmt.where(or_(
                Company.name.ilike(f"%{q}%"),
                Company.address.ilike(f"%{q}%")
            ))

        result = await session.execute(stmt)
        all_rows = result.scalars().all()
        total = len(all_rows)
        items = all_rows[(page - 1) * size : (page - 1) * size + size]

    return templates.TemplateResponse(
        "companies.html",
        {"request": request, "items": items, "page": page, "size": size, "total": total, "q": q or ""}
    )

# ---------------------------------------------------------
# API: Add New Company (Fixes the 405 Error)
# ---------------------------------------------------------
@router.post("/companies")
async def add_new_company(request: Request, data: AddCompanyRequest, bg_tasks: BackgroundTasks):
    uid = _require_user(request)
    if not uid:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)

    async with get_session() as session:
        # Check if company already added by this user
        existing = await session.execute(
            select(Company).where(
                Company.google_place_id == data.google_place_id,
                Company.owner_id == uid
            )
        )
        if existing.scalar_one_or_none():
            return JSONResponse({"success": False, "message": "Company already exists in your list"}, status_code=400)

        new_company = Company(
            name=data.name,
            google_place_id=data.google_place_id,
            address=data.address,
            owner_id=uid
        )

        session.add(new_company)
        await session.flush() # Get the ID before commit

        # Log the action
        session.add(AuditLog(user_id=uid, action="company_add", meta={"company_id": new_company.id}))
        
        await session.commit()

        # Trigger background review sync
        bg_tasks.add_task(ingest_company_reviews, new_company.google_place_id, new_company.id)

    return {
        "success": True, 
        "message": "Company added and sync started!",
        "redirect": "/dashboard"
    }

# ---------------------------------------------------------
# API: Delete Company
# ---------------------------------------------------------
@router.post("/companies/{company_id}/delete")
async def company_delete(company_id: int, request: Request):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse("/login", status_code=302)

    async with get_session() as session:
        # Verify ownership before delete
        check = await session.execute(select(Company).where(Company.id == company_id, Company.owner_id == uid))
        company = check.scalar_one_or_none()
        
        if not company:
            raise HTTPException(status_code=404, detail="Company not found or access denied")

        await session.delete(company)
        
        # Log deletion
        session.add(AuditLog(user_id=uid, action="company_delete", meta={"company_id": company_id}))
        await session.commit()

    return RedirectResponse("/api/companies", status_code=303)

# ---------------------------------------------------------
# API: Manual Sync Trigger
# ---------------------------------------------------------
@router.post("/companies/{company_id}/sync")
async def company_sync(company_id: int, request: Request, bg_tasks: BackgroundTasks):
    uid = _require_user(request)
    if not uid:
        return JSONResponse({"success": False}, status_code=401)

    async with get_session() as session:
        res = await session.execute(select(Company).where(Company.id == company_id, Company.owner_id == uid))
        company = res.scalar_one_or_none()
        
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        bg_tasks.add_task(ingest_company_reviews, company.google_place_id, company.id)
        await session.commit()

    return {"success": True, "message": "Sync background task triggered."}
