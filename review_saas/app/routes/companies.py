# filename: app/routes/companies.py
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
router = APIRouter(tags=["companies"])
templates = Jinja2Templates(directory="app/templates")

# --- Helper: Authentication ---
def _require_user(request: Request):
    return request.session.get("user_id")

# --- Pydantic Schemas ---
class PlaceSearchResult(BaseModel):
    place_id: str
    name: str
    formatted_address: str | None = None

class AddCompanyRequest(BaseModel):
    name: str
    place_id: str
    address: str | None = None
    google_data: dict | None = None

# --- Helper: Get Updated List Logic (Database Fetch) ---
async def _get_companies_data(session, uid: int):
    """
    Core logic to fetch data from the database. 
    Ensures front-end display stays in sync with actual DB state.
    """
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

# --- UI Route: Companies Management Page ---
@router.get("/companies", response_class=HTMLResponse)
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
        {
            "request": request,
            "items": items,
            "page": page,
            "size": size,
            "total": total,
            "q": q or "",
        },
    )

# --- API: List Companies (Fetch from Database) ---
@router.get("/api/companies/list")
async def list_companies(request: Request):
    uid = _require_user(request)
    if not uid:
        return JSONResponse({"success": False, "companies": [], "message": "Unauthorized"}, status_code=401)

    async with get_session() as session:
        data = await _get_companies_data(session, uid)
    return {"success": True, "companies": data}

# --- API: Search Google Places (Input from Google API) ---
@router.get("/google/places/search")
async def search_google_places(q: str = Query(..., min_length=3)):
    try:
        gmaps_client = googlemaps.Client(key=settings.GOOGLE_PLACES_API_KEY)
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

# --- API: Add New Company (Input -> Database -> Fetch -> Display) ---
@router.post("/companies/add")
async def add_new_company(request: Request, data: AddCompanyRequest, bg_tasks: BackgroundTasks):
    uid = _require_user(request)
    if not uid:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)

    async with get_session() as session:
        # Check for duplication
        existing = await session.execute(
            select(Company).where(Company.google_place_id == data.place_id, Company.owner_id == uid)
        )
        if existing.scalar_one_or_none():
            return JSONResponse({"success": False, "message": "Company already exists in your account"}, status_code=400)

        # 1. DATABASE INPUT: Save record to Postgres
        new_company = Company(
            name=data.name,
            google_place_id=data.place_id,
            address=data.address,
            google_data=data.google_data or {},
            owner_id=uid,
        )
        session.add(new_company)
        await session.flush() # Generate ID for Audit Log

        # 2. AUDIT LOG: Track activity
        session.add(AuditLog(user_id=uid, action="company_add_google", meta={"company_id": new_company.id}))

        # 3. COMMIT TRANSACTION: Hard-save to DB before responding
        await session.commit()
        await session.refresh(new_company)

        # 4. BACKGROUND PROCESS: Start scraping reviews
        bg_tasks.add_task(ingest_company_reviews, new_company.id, new_company.google_place_id)

        # 5. DATABASE FETCH: Get full updated list for front-end refresh
        companies = await _get_companies_data(session, uid)
        
    return {
        "success": True,
        "company": {"id": new_company.id, "name": new_company.name},
        "companies": companies, 
        "message": "Company saved! Refreshing your list..."
    }

# --- API: Sync/Refresh Company ---
@router.post("/companies/{company_id}/sync")
async def company_sync(company_id: int, request: Request, bg_tasks: BackgroundTasks):
    uid = _require_user(request)
    if not uid:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)

    async with get_session() as session:
        result = await session.execute(select(Company).where(Company.id == company_id, Company.owner_id == uid))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Trigger background scraper
        bg_tasks.add_task(ingest_company_reviews, company.id, company.google_place_id)
        session.add(AuditLog(user_id=uid, action="company_sync_triggered", meta={"company_id": company.id}))
        await session.commit()
        
        # DATABASE FETCH: Refresh display data
        companies = await _get_companies_data(session, uid)

    return {"success": True, "message": "Review sync started!", "companies": companies}

# --- POST: Delete Company ---
@router.post("/companies/{company_id}/delete")
async def company_delete(request: Request, company_id: int):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse("/login", status_code=302)

    async with get_session() as session:
        await session.execute(delete(Company).where(Company.id == company_id, Company.owner_id == uid))
        session.add(AuditLog(user_id=uid, action="company_delete", meta={"company_id": company_id}))
        await session.commit()

    return RedirectResponse("/companies", status_code=302)
