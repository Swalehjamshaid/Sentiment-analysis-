from __future__ import annotations
import logging
import googlemaps
from fastapi import APIRouter, Request, BackgroundTasks, Query, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import select, delete, or_, func, desc
from pydantic import BaseModel, ValidationError
from app.core.db import get_session
from app.core.models import Company, AuditLog, User, Review
from app.core.config import settings
from app.services.google_reviews import ingest_company_reviews

logger = logging.getLogger(__name__)

# Router with prefix="/api" — matches the log path
router = APIRouter(prefix="/api", tags=["companies"])

templates = Jinja2Templates(directory="app/templates")

# ---------------------------------------------------------
# Helper: Authentication
# ---------------------------------------------------------
def _require_user(request: Request) -> int | None:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id

# ---------------------------------------------------------
# Safe Google Maps Client
# ---------------------------------------------------------
def _get_gmaps_client():
    if not settings.GOOGLE_PLACES_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Google Places API key is not configured in settings."
        )
    return googlemaps.Client(key=settings.GOOGLE_PLACES_API_KEY)

# ---------------------------------------------------------
# Pydantic Models
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
# Helper: Get companies with stats
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
# UI: Companies page (override prefix for clean URL)
# ---------------------------------------------------------
@router.get("/companies", response_class=HTMLResponse, include_in_schema=False)
async def companies_page(
    request: Request,
    q: str | None = None,
    page: int = 1,
    size: int = 10
):
    uid = _require_user(request)
    async with get_session() as session:
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
# API: List companies
# ---------------------------------------------------------
@router.get("/companies/list")
async def list_companies(request: Request):
    uid = _require_user(request)
    async with get_session() as session:
        data = await _get_companies_data(session, uid)
    return {"success": True, "companies": data}

# ---------------------------------------------------------
# API: Search Google Places
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
        logger.error(f"Google Places search failed: {e}", exc_info=True)
        return {"success": False, "message": str(e)}

# ---------------------------------------------------------
# API: Add new company — FIXED: path changed to /companies (matches form action)
# ---------------------------------------------------------
@router.post("/companies")   # ← CHANGED FROM "/companies/add"
async def add_new_company(
    request: Request,
    data: AddCompanyRequest,
    bg_tasks: BackgroundTasks
):
    uid = _require_user(request)
    async with get_session() as session:
        # Check duplicate
        existing = await session.execute(
            select(Company).where(
                Company.google_place_id == data.place_id,
                Company.owner_id == uid,
            )
        )
        if existing.scalar_one_or_none():
            return JSONResponse(
                {"success": False, "message": "This place is already added for your account"},
                status_code=400
            )

        # Create company
        new_company = Company(
            name=data.name.strip(),
            google_place_id=data.place_id,
            address=data.address.strip() if data.address else None,
            owner_id=uid,
        )
        session.add(new_company)
        await session.flush()  # get ID

        # Audit log
        session.add(
            AuditLog(
                user_id=uid,
                action="company_add_google",
                meta={"company_id": new_company.id, "place_id": data.place_id},
            )
        )

        await session.commit()
        await session.refresh(new_company)

        # Background sync
        bg_tasks.add_task(
            ingest_company_reviews,
            place_id=new_company.google_place_id,
            company_id=new_company.id
        )

        # Return updated list
        companies = await _get_companies_data(session, uid)

    logger.info(f"Company added: {new_company.name} (ID: {new_company.id}) by user {uid}")

    return {
        "success": True,
        "company": {
            "id": new_company.id,
            "name": new_company.name,
            "place_id": new_company.google_place_id
        },
        "companies": companies,
        "message": "Company added successfully. Review sync started in background."
    }

# ---------------------------------------------------------
# API: Sync reviews for existing company
# ---------------------------------------------------------
@router.post("/companies/{company_id}/sync")
async def company_sync(
    company_id: int,
    request: Request,
    bg_tasks: BackgroundTasks
):
    uid = _require_user(request)
    async with get_session() as session:
        company = await session.get(Company, company_id)
        if not company or company.owner_id != uid:
            raise HTTPException(404, "Company not found or not owned by you")

        bg_tasks.add_task(
            ingest_company_reviews,
            place_id=company.google_place_id,
            company_id=company.id
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
        "message": "Review sync triggered successfully",
        "companies": companies
    }

# ---------------------------------------------------------
# DELETE: Remove company
# ---------------------------------------------------------
@router.post("/companies/{company_id}/delete")
async def company_delete(request: Request, company_id: int):
    uid = _require_user(request)
    async with get_session() as session:
        stmt = delete(Company).where(
            Company.id == company_id,
            Company.owner_id == uid
        )
        result = await session.execute(stmt)
        if result.rowcount == 0:
            raise HTTPException(404, "Company not found")

        session.add(
            AuditLog(
                user_id=uid,
                action="company_delete",
                meta={"company_id": company_id},
            )
        )
        await session.commit()

    return RedirectResponse("/companies", status_code=302)
