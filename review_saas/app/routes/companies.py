# filename: app/routes/companies.py
from __future__ import annotations
from fastapi import APIRouter, Request, Form, Query, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import select, delete, or_
from app.core.db import get_session
from app.core.models import Company, AuditLog
from app.core.config import settings
from app.services.google_reviews import ingest_company_reviews
from pydantic import BaseModel
import googlemaps

router = APIRouter(tags=['companies'])
templates = Jinja2Templates(directory='app/templates')

def _require_user(request: Request):
    return request.session.get('user_id')

# --- VIEW COMPANIES ---
@router.get('/companies', response_class=HTMLResponse)
async def companies_page(request: Request, q: str | None = None, page: int = 1, size: int = 10):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse('/login', status_code=302)

    async with get_session() as session:
        stmt = select(Company).order_by(Company.created_at.desc())
        if q:
            stmt = stmt.where(or_(Company.name.ilike(f"%{q}%"), Company.address.ilike(f"%{q}%")))
        result = await session.execute(stmt)
        all_rows = result.scalars().all()
        total = len(all_rows)
        items = all_rows[(page-1)*size:(page-1)*size+size]

    return templates.TemplateResponse("companies.html", {
        "request": request,
        "items": items,
        "page": page,
        "size": size,
        "total": total,
        "q": q or ""
    })

# --- MANUAL SYNC / BACKGROUND FETCH ---
@router.post("/companies/{company_id}/sync")
async def company_sync(company_id: int, request: Request, bg_tasks: BackgroundTasks):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse("/login", status_code=302)

    async with get_session() as session:
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Trigger background fetch
        bg_tasks.add_task(ingest_company_reviews, session, company.id, company.place_id)

        session.add(AuditLog(user_id=uid, action="company_sync_triggered", meta={"company_id": company.id}))
        await session.commit()

    return RedirectResponse(url=f"/dashboard?company_id={company_id}", status_code=302)

# --- GOOGLE PLACE SEARCH ---
class PlaceSearchResult(BaseModel):
    place_id: str
    name: str
    formatted_address: str | None = None

@router.get("/google/places/search")
async def search_google_places(q: str = Query(..., min_length=3)):
    try:
        gmaps = googlemaps.Client(key=settings.GOOGLE_PLACES_API_KEY)
        result = gmaps.places(query=q, location="33.6844,73.0479", radius=200000)
        places = [
            PlaceSearchResult(
                place_id=p["place_id"],
                name=p["name"],
                formatted_address=p.get("formatted_address")
            ) for p in result.get("results", [])
        ]
        return {"success": True, "results": places}
    except Exception as e:
        return {"success": False, "message": str(e)}

# --- ADD NEW COMPANY FROM GOOGLE SEARCH ---
class AddCompanyRequest(BaseModel):
    name: str
    place_id: str
    address: str | None = None
    google_data: dict | None = None

@router.post("/companies/add")
async def add_new_company(request: Request, data: AddCompanyRequest, bg_tasks: BackgroundTasks):
    uid = _require_user(request)
    if not uid:
        return {"success": False, "message": "Unauthorized"}

    async with get_session() as session:
        # Prevent duplicates
        res = await session.execute(select(Company).where(Company.place_id == data.place_id))
        if res.scalar_one_or_none():
            return {"success": False, "message": "Company already exists"}

        new_company = Company(
            name=data.name,
            place_id=data.place_id,
            address=data.address,
            google_data=data.google_data or {},
            owner_id=uid
        )
        session.add(new_company)
        await session.flush()

        # Trigger background ingestion
        bg_tasks.add_task(ingest_company_reviews, session, new_company.id, new_company.place_id)

        session.add(AuditLog(user_id=uid, action="company_add_google", meta={"company_id": new_company.id}))
        await session.commit()

        return {"success": True, "company_id": new_company.id, "message": "Company added and reviews loading!"}

# --- DELETE COMPANY ---
@router.post("/companies/{company_id}/delete")
async def company_delete(request: Request, company_id: int):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse("/login", status_code=302)

    async with get_session() as session:
        await session.execute(delete(Company).where(Company.id == company_id))
        session.add(AuditLog(user_id=uid, action="company_delete", meta={"company_id": company_id}))
        await session.commit()

    return RedirectResponse("/companies", status_code=302)
