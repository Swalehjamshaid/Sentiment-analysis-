# filename: app/routes/companies.py
from __future__ import annotations
from fastapi import APIRouter, Request, Form, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import select, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.models import Company, AuditLog
from app.core.config import settings
from app.services.google_reviews import ingest_company_reviews
import googlemaps
from pydantic import BaseModel

router = APIRouter(tags=['companies'])
templates = Jinja2Templates(directory='app/templates')

def _require_user(request: Request):
    return request.session.get('user_id')

# ──────────────────────────────────────────────────────────────
# Existing endpoints (preserved)
# ──────────────────────────────────────────────────────────────

@router.get('/companies', response_class=HTMLResponse)
async def companies_page(request: Request, q: str | None = None, rating: float | None = None, category: str | None = None, location: str | None = None, page: int = 1, size: int = 10):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse('/login', status_code=302)
    async with get_session() as session:
        stmt = select(Company).order_by(Company.created_at.desc())
        if q:
            stmt = stmt.where(or_(Company.name.ilike(f'%{q}%'), Company.address.ilike(f'%{q}%')))
        if rating:
            stmt = stmt.where(Company.avg_rating >= rating)
        if category:
            stmt = stmt.where(Company.category.ilike(f'%{category}%'))
        if location:
            stmt = stmt.where(Company.address.ilike(f'%{location}%'))
        
        result = await session.execute(stmt)
        all_rows = result.scalars().all()
        total = len(all_rows)
        items = all_rows[(page-1)*size: (page-1)*size+size]
    return templates.TemplateResponse('companies.html', {"request": request, "items": items, "page": page, "size": size, "total": total, "q": q or ''})

@router.post('/companies/create')
async def company_create(request: Request, name: str = Form(...), place_id: str = Form(''), address: str = Form(''), phone: str = Form(''), website: str = Form(''), category: str = Form(''), hours: str = Form('')):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse('/login', status_code=302)
    async with get_session() as session:
        c = Company(name=name, place_id=(place_id or None), address=address or None, phone=phone or None, website=website or None, category=category or None, hours=hours or None, owner_id=uid)
        session.add(c)
        await session.commit()
        session.add(AuditLog(user_id=uid, action='company_create', meta={'company_id': c.id}))
        await session.commit()
    return RedirectResponse('/companies', status_code=302)

@router.post('/companies/{company_id}/delete')
async def company_delete(request: Request, company_id: int):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse('/login', status_code=302)
    async with get_session() as session:
        await session.execute(delete(Company).where(Company.id==company_id))
        await session.commit()
        session.add(AuditLog(user_id=uid, action='company_delete', meta={'company_id': company_id}))
        await session.commit()
    return RedirectResponse('/companies', status_code=302)

@router.post('/companies/{company_id}/sync')
async def company_sync(company_id: int, request: Request):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse('/login', status_code=302)
    async with get_session() as session:
        result = await session.execute(select(Company).where(Company.id==company_id))
        c = result.scalar_one_or_none()
        if not c:
            raise HTTPException(status_code=404, detail='Company not found')
        stats = await ingest_company_reviews(session, c)
        await session.commit()
        session.add(AuditLog(user_id=uid, action='company_sync', meta={'company_id': c.id, 'ingested': stats}))
        await session.commit()
    return RedirectResponse(url=f'/dashboard?company_id={company_id}', status_code=302)

# ──────────────────────────────────────────────────────────────
# Google Places & Maps API Integration
# ──────────────────────────────────────────────────────────────

class PlaceSearchResult(BaseModel):
    place_id: str
    name: str
    formatted_address: str | None = None
    vicinity: str | None = None

@router.get("/google/places/search")
async def search_google_places(q: str = Query(..., min_length=3)):
    """
    Search Google Places API for companies/locations
    """
    try:
        gmaps = googlemaps.Client(key=settings.GOOGLE_PLACES_API_KEY)
        # Bias toward Pakistan
        result = gmaps.places(query=q, location="33.6844,73.0479", radius=200000)
        
        places = []
        for p in result.get("results", []):
            places.append(PlaceSearchResult(
                place_id=p["place_id"],
                name=p["name"],
                formatted_address=p.get("formatted_address"),
                vicinity=p.get("vicinity")
            ))
        
        return {"success": True, "results": places}
    except Exception as e:
        return {"success": False, "message": str(e)}

class AddCompanyRequest(BaseModel):
    name: str
    place_id: str
    address: str | None = None
    google_data: dict | None = None

@router.post("/companies/add")
async def add_new_company(request: Request, data: AddCompanyRequest):
    """
    Add a new company from Google Places search result.
    Uses 'async with get_session()' to ensure proper session handling.
    """
    uid = _require_user(request)
    # Note: Requirement specified user tracking, so we capture UID if available
    
    async with get_session() as session:
        # Prevent duplicate by place_id
        result = await session.execute(
            select(Company).where(Company.place_id == data.place_id)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            return {"success": False, "message": "Company with this place_id already exists"}

        new_company = Company(
            name=data.name,
            place_id=data.place_id,
            address=data.address,
            google_data=data.google_data or {},
            owner_id=uid # Link to logged in user
        )

        session.add(new_company)
        await session.flush() # Get ID before commit
        
        if uid:
            session.add(AuditLog(user_id=uid, action='company_add_google', meta={'company_id': new_company.id}))
        
        await session.commit()

        return {
            "success": True,
            "company_id": new_company.id,
            "name": new_company.name,
            "message": "Company added successfully"
        }
