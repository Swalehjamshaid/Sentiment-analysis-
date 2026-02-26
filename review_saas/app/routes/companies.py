from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette import status

from app.db import get_db
from app.models import Company
from app.dependencies import get_current_user  # your existing auth dependency

router = APIRouter()


# =========================================================
# ✅ CREATE COMPANY (Works with your existing modal form)
# Route matches: action="/companies/create"
# =========================================================
@router.post("/companies/create")
def create_company(
    request: Request,
    place_id: str = Form(None),
    name: str = Form(None),
    address: str = Form(None),
    city: str = Form(None),
    state: str = Form(None),
    postal_code: str = Form(None),
    country: str = Form(None),
    latitude: float = Form(None),
    longitude: float = Form(None),
    phone: str = Form(None),
    website: str = Form(None),
    google_url: str = Form(None),
    rating: float = Form(None),
    user_ratings_total: int = Form(None),
    types: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Prevent duplicate same place_id for same user
    existing = db.query(Company).filter(
        Company.place_id == place_id,
        Company.user_id == current_user.id
    ).first()

    if existing:
        return RedirectResponse(
            url=f"/dashboard/{existing.id}",
            status_code=status.HTTP_302_FOUND
        )

    company = Company(
        user_id=current_user.id,
        place_id=place_id,
        name=name,
        address=address,
        city=city,
        state=state,
        postal_code=postal_code,
        country=country,
        latitude=latitude,
        longitude=longitude,
        phone=phone,
        website=website,
        google_url=google_url,
        rating=rating,
        user_ratings_total=user_ratings_total,
        types=types
    )

    db.add(company)
    db.commit()
    db.refresh(company)

    return RedirectResponse(
        url=f"/dashboard/{company.id}",
        status_code=status.HTTP_302_FOUND
    )


# =========================================================
# ✅ DELETE COMPANY
# You can call: POST /companies/delete/{company_id}
# =========================================================
@router.post("/companies/delete/{company_id}")
def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    company = db.query(Company).filter(
        Company.id == company_id,
        Company.user_id == current_user.id
    ).first()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    db.delete(company)
    db.commit()

    return RedirectResponse(
        url="/dashboard",
        status_code=status.HTTP_302_FOUND
    )
