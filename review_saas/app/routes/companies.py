# FILE: app/routes/companies.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime
import requests
import os

from ..db import get_db
from ..models import Company
from ..schemas import CompanyCreate, CompanyResponse

router = APIRouter(prefix="/api/companies", tags=["companies"])

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")


# ============================================================
# 1️⃣ GET ALL COMPANIES (FOR DASHBOARD DROPDOWN)
# ============================================================

@router.get("/", response_model=List[CompanyResponse])
def get_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).filter(Company.status == "active").all()
    return companies


# ============================================================
# 2️⃣ ADD COMPANY (FROM GOOGLE AUTOFILL)
# ============================================================

@router.post("/", response_model=CompanyResponse, status_code=201)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)):

    # Prevent duplicate by place_id
    if payload.place_id:
        existing = db.query(Company).filter(
            Company.place_id == payload.place_id
        ).first()
        if existing:
            raise HTTPException(409, "Company already exists with this Place ID")

    # Enrich using Google Places
    lat = lng = phone = address = city = None
    name = payload.name

    if payload.place_id and GOOGLE_PLACES_API_KEY:
        try:
            url = "https://maps.googleapis.com/maps/api/place/details/json"
            params = {
                "place_id": payload.place_id,
                "fields": "name,formatted_address,formatted_phone_number,address_components,geometry",
                "key": GOOGLE_PLACES_API_KEY,
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            result = response.json().get("result", {})

            name = result.get("name", payload.name)
            address = result.get("formatted_address")
            phone = result.get("formatted_phone_number")

            # Extract city
            for comp in result.get("address_components", []):
                if "locality" in comp.get("types", []):
                    city = comp.get("long_name")
                    break

            location = result.get("geometry", {}).get("location", {})
            lat = location.get("lat")
            lng = location.get("lng")

        except Exception as e:
            raise HTTPException(502, f"Google Places error: {str(e)}")

    new_company = Company(
        name=name,
        place_id=payload.place_id,
        city=city,
        lat=lat,
        lng=lng,
        email=payload.email,
        phone=phone,
        address=address,
        description=payload.description,
        status="active",
        created_at=datetime.utcnow()
    )

    db.add(new_company)
    db.commit()
    db.refresh(new_company)

    return new_company


# ============================================================
# 3️⃣ GOOGLE AUTOCOMPLETE (FOR SEARCH BOX)
# ============================================================

@router.get("/autocomplete", response_model=List[Dict[str, str]])
def autocomplete_company(q: str = Query(..., min_length=2)):

    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": q,
        "types": "establishment",
        "key": GOOGLE_PLACES_API_KEY,
    }

    response = requests.get(url, params=params, timeout=8)
    response.raise_for_status()
    data = response.json()

    return [
        {
            "description": p.get("description"),
            "place_id": p.get("place_id")
        }
        for p in data.get("predictions", [])
    ]
