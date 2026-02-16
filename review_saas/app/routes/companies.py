# review_saas/app/routes/companies.py
from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import or_
from typing import Optional, List

from ..db import engine
from .. import models

router = APIRouter(prefix="/api/companies", tags=["companies"])

# Session factory + dependency
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def maps_url_from_place_id(place_id: Optional[str]) -> Optional[str]:
    if not place_id:
        return None
    # Google Maps shareable URL format for a place_id
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"


@router.get("", response_model=List[dict])
def list_companies(db: Session = Depends(get_db)):
    """
    Minimal listing endpoint for quick verification.
    """
    rows = db.query(models.Company).order_by(models.Company.id.desc()).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "city": r.city,
            "place_id": r.place_id,
            "maps_url": r.maps_url,
            "status": r.status,
            "logo_url": r.logo_url,
            "owner_user_id": r.owner_user_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_company(
    # HTML <form> fields
    name: str = Form(...),
    city: str = Form(...),
    place_id: Optional[str] = Form(None),
    # Optional extras if you add hidden fields later
    maps_url: Optional[str] = Form(None),
    status_value: Optional[str] = Form(None),  # e.g., "Active" / "Paused"
    logo_url: Optional[str] = Form(None),
    owner_user_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Creates a company based on an HTML <form> submission.

    - Path is /api/companies (NO trailing slash) to match your template form action.
    - Enforces your composite uniqueness by (owner_user_id, place_id) and (owner_user_id, name).
    - If maps_url not provided, we derive it from place_id.
    """

    # Normalize inputs
    name_clean = (name or "").strip()
    city_clean = (city or "").strip()
    place_id_clean = (place_id or "").strip() or None
    status_clean = (status_value or "").strip() or None

    if not name_clean:
        raise HTTPException(status_code=422, detail="Company name is required.")
    if not city_clean:
        raise HTTPException(status_code=422, detail="City is required.")

    # Duplicate checks consistent with your UniqueConstraints:
    # UniqueConstraint('owner_user_id', 'place_id')
    if place_id_clean:
        if owner_user_id is None:
            existing = (
                db.query(models.Company)
                .filter(
                    models.Company.owner_user_id.is_(None),
                    models.Company.place_id == place_id_clean,
                )
                .first()
            )
        else:
            existing = (
                db.query(models.Company)
                .filter(
                    models.Company.owner_user_id == owner_user_id,
                    models.Company.place_id == place_id_clean,
                )
                .first()
            )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A company with this Google Place ID already exists for this owner.",
            )

    # UniqueConstraint('owner_user_id', 'name')
    if owner_user_id is None:
        name_dup = (
            db.query(models.Company)
            .filter(
                models.Company.owner_user_id.is_(None),
                models.Company.name == name_clean,
            )
            .first()
        )
    else:
        name_dup = (
            db.query(models.Company)
            .filter(
                models.Company.owner_user_id == owner_user_id,
                models.Company.name == name_clean,
            )
            .first()
        )
    if name_dup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A company with this name already exists for this owner.",
        )

    # Derive maps_url from place_id if not provided
    final_maps_url = maps_url or maps_url_from_place_id(place_id_clean)

    company = models.Company(
        owner_user_id=owner_user_id,
        name=name_clean,
        place_id=place_id_clean,
        maps_url=final_maps_url,
        city=city_clean,
        status=status_clean or "Active",  # your model default is 'Active'
        logo_url=logo_url,
    )

    db.add(company)
    db.commit()
    db.refresh(company)

    return {
        "ok": True,
        "company": {
            "id": company.id,
            "name": company.name,
            "city": company.city,
            "place_id": company.place_id,
            "maps_url": company.maps_url,
            "status": company.status,
            "logo_url": company.logo_url,
            "owner_user_id": company.owner_user_id,
            "created_at": company.created_at.isoformat() if company.created_at else None,
        },
    }
