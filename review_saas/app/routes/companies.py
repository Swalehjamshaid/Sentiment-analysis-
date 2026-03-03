# filename: app/routes/companies.py
from __future__ import annotations
from fastapi import APIRouter, Request, Form, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import select, delete, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.models import Company, AuditLog
from app.core.config import settings
from app.services.google_reviews import ingest_company_reviews
from googlemaps import Client
from pydantic import BaseModel

router = APIRouter(tags=['companies'])
templates = Jinja2Templates(directory='app/templates')

def _require_user(request: Request):
    return request.session.get('user_id')

# ──────────────────────────────────────────────────────────────
# Existing endpoints (completely unchanged)
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
        # location simplistic filter inside address
        if location:
            stmt = stmt.where(Company.address.ilike(f'%{location}%'))
        all_rows = (await session.execute(stmt)).scalars().all()
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
        c = (await session.execute(select(Company).where(Company.id==company_id))).scalar_one_or_none()
        if not c:
            raise HTTPException(status_code=404, detail='Company not found')
        old = c.avg_rating
        stats = await ingest_company_reviews(session, c)
        await session.commit()
        session.add(AuditLog(user_id=uid, action='company_sync', meta={'company_id': c.id, 'ingested': stats}))
        await session.commit()
    return RedirectResponse(url=f'/dashboard?company_id={company_id}', status_code=302)

# ──────────────────────────────────────────────────────────────
# NEW: Google Places API Integration
# ──────────────────────────────────────────────────────────────

class PlaceSearchResult(BaseModel):
    place_id: str
    name: str
    formatted_address: str | None = None
    vicinity: str | None = None

@router.get("/google/places/search")
async def search_google_places(q: str = Query(min_length=3)):
    """
    Search Google Places API for companies/locations
    Used by the dashboard modal to find places
    """
    try:
        gmaps = Client(key=settings.GOOGLE_PLACES_API_KEY)
        # Bias toward Pakistan (centered on Lahore/Rawalpindi area, 200km radius)
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
async def add_new_company(data: AddCompanyRequest, session: AsyncSession = Depends(get_session)):
    """
    Add a new company from Google Places search result
    Used by the dashboard modal after user selects a place
    """
    # Prevent duplicate by place_id
    existing = await session.execute(
        select(Company).where(Company.place_id == data.place_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Company with this place_id already exists")

    new_company = Company(
        name=data.name,
        place_id=data.place_id,
        address=data.address,
        google_data=data.google_data or {},
        # If you have user auth, you can add owner_id here
        # owner_id = current_user.id (add Depends on auth if needed)
    )

    session.add(new_company)
    await session.commit()
    await session.refresh(new_company)

    # Optional: log the action (uncomment if you want audit)
    # session.add(AuditLog(user_id=..., action='company_add', meta={'company_id': new_company.id}))
    # await session.commit()

    return {
        "success": True,
        "company_id": new_company.id,
        "name": new_company.name,
        "message": "Company added successfully"
    }
