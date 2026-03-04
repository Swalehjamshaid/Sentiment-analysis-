# filename: app/routes/companies.py
from __future__ import annotations
from fastapi import APIRouter, Request, JSONResponse
from sqlalchemy import select, or_, func
from app.core.db import get_session
from app.core.models import Company, Review, User

router = APIRouter(tags=["companies"])

def _require_user(request: Request):
    return request.session.get("user_id")


@router.get("/api/companies/list")
async def list_companies(request: Request, q: str | None = None):
    """
    Returns companies in JSON for dashboard frontend.
    Computes avg_rating and review_count dynamically.
    Shows only companies for the logged-in user.
    """
    uid = _require_user(request)
    if not uid:
        return JSONResponse({"success": False, "results": [], "message": "Unauthorized"}, status_code=401)

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

        # Build correct JSON keys that match frontend expectations
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

        return {"success": True, "companies": data}  # <-- key is now 'companies' to match JS
