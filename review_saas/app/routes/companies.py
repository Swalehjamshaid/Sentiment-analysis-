# filename: app/routes/companies.py
from __future__ import annotations
from fastapi import APIRouter, Request, BackgroundTasks, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import select, delete, or_, func
from app.core.db import get_session
from app.core.models import Company, AuditLog, User
from app.core.config import settings
from app.services.google_reviews import ingest_company_reviews
from pydantic import BaseModel
import googlemaps
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["companies"])
templates = Jinja2Templates(directory="app/templates")


def _require_user(request: Request):
    return request.session.get("user_id")


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


@router.get("/api/companies/list")
async def list_companies(request: Request, q: str | None = None):
    uid = _require_user(request)
    if not uid:
        return JSONResponse({"success": False, "companies": [], "message": "Unauthorized"}, status_code=401)

    async with get_session() as session:
        stmt = (
            select(
                Company.id,
                Company.name,
                Company.address,
                Company.google_place_id,
                func.coalesce(func.avg(Review.rating), 0).label("avg_rating"),
                func.count(Review.id).label("review_count")
            )
            .outerjoin(Review, Review.company_id == Company.id)
            .where(Company.owner_id == uid)
            .group_by(Company.id)
            .order_by(Company.created_at.desc())
        )

        if q:
            stmt = stmt.where(
                or_(
                    Company.name.ilike(f"%{q}%"),
                    Company.address.ilike(f"%{q}%")
                )
            )

        result = await session.execute(stmt)
        companies = result.all()

        data = [
            {
                "id": c.id,
                "name": c.name,
                "address": c.address or "",
                "place_id": c.google_place_id or "",
                "avg_rating": round(c.avg_rating or 0, 2),
                "review_count": c.review_count,
            }
            for c in companies
        ]

    return {"success": True, "companies": data}


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
                formatted_address=p.get("formatted_address"),
            )
            for p in result.get("results", [])
        ]

        return {"success": True, "results": places}

    except Exception as e:
        logger.error(f"Google search error: {e}")
        return {"success": False, "message": str(e)}


class AddCompanyRequest(BaseModel):
    name: str
    place_id: str
    address: str | None = None
    google_data: dict | None = None


@router.post("/companies/add")
async def add_new_company(request: Request, data: AddCompanyRequest, bg_tasks: BackgroundTasks):
    uid = _require_user(request)
    if not uid:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)

    async with get_session() as session:
        user_result = await session.execute(select(User).where(User.id == uid))
        user = user_result.scalar_one_or_none()
        if not user:
            request.session.clear()
            return JSONResponse({"success": False, "message": "Session expired"}, status_code=401)

        existing = await session.execute(
            select(Company).where(Company.google_place_id == data.place_id, Company.owner_id == uid)
        )
        if existing.scalar_one_or_none():
            return {"success": False, "message": "Company already exists"}

        new_company = Company(
            name=data.name,
            google_place_id=data.place_id,
            address=data.address,
            google_data=data.google_data or {},
            owner_id=user.id,
        )

        session.add(new_company)
        await session.flush()

        # Add background task for Google reviews
        bg_tasks.add_task(
            ingest_company_reviews,
            new_company.id,
            new_company.google_place_id,
        )

        session.add(
            AuditLog(
                user_id=user.id,
                action="company_add_google",
                meta={"company_id": new_company.id},
            )
        )

        await session.commit()

        return {
            "success": True,
            "company": {
                "id": new_company.id,
                "name": new_company.name,
                "address": new_company.address,
                "avg_rating": 0.0,
                "review_count": 0,
            },
            "message": "Company added and reviews loading!",
        }


@router.post("/companies/{company_id}/sync")
async def company_sync(company_id: int, request: Request, bg_tasks: BackgroundTasks):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse("/login", status_code=302)

    async with get_session() as session:
        user_check = await session.execute(select(User).where(User.id == uid))
        if not user_check.scalar_one_or_none():
            request.session.clear()
            return RedirectResponse("/login", status_code=302)

        result = await session.execute(select(Company).where(Company.id == company_id, Company.owner_id == uid))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Trigger ingestion for this company
        bg_tasks.add_task(
            ingest_company_reviews,
            company.id,
            company.google_place_id,
        )

        session.add(
            AuditLog(
                user_id=uid,
                action="company_sync_triggered",
                meta={"company_id": company.id},
            )
        )

        await session.commit()

    return RedirectResponse(url=f"/dashboard?company_id={company_id}", status_code=302)


@router.post("/companies/{company_id}/delete")
async def company_delete(request: Request, company_id: int):
    uid = _require_user(request)
    if not uid:
        return RedirectResponse("/login", status_code=302)

    async with get_session() as session:
        await session.execute(delete(Company).where(Company.id == company_id, Company.owner_id == uid))

        session.add(
            AuditLog(
                user_id=uid,
                action="company_delete",
                meta={"company_id": company_id},
            )
        )

        await session.commit()

    return RedirectResponse("/companies", status_code=302)
