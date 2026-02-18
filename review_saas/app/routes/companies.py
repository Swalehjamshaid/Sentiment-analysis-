# Filename: app/routes/companies.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Company
from typing import List
import requests
from datetime import datetime
import os

router = APIRouter(prefix="/companies", tags=["companies"])

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # Make sure your API key is set in environment

# --- List all companies ---
@router.get("/", response_model=List[dict])
def list_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).all()
    return [{"name": c.name, "city": c.city, "status": c.status} for c in companies]

# --- Add a new company (optionally via Google Place ID) ---
@router.post("/")
def add_company(
    name: str = Query(...),
    city: str = Query(None),
    place_id: str = Query(None),
    db: Session = Depends(get_db)
):
    if place_id:
        url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&key={GOOGLE_API_KEY}"
        resp = requests.get(url)
        if resp.status_code == 200:
            data = resp.json().get("result", {})
            name = data.get("name", name)
            # Extract city from address components
            if "address_components" in data:
                for comp in data["address_components"]:
                    if "locality" in comp.get("types", []):
                        city = comp.get("long_name")
                        break
        else:
            raise HTTPException(status_code=502, detail="Failed to fetch details from Google API")

    new_company = Company(
        name=name,
        city=city,
        status="active",
        created_at=datetime.utcnow(),
        place_id=place_id
    )
    db.add(new_company)
    db.commit()
    db.refresh(new_company)
    return {"name": new_company.name, "city": new_company.city, "status": new_company.status}

# --- Autocomplete companies using Google Places API ---
@router.get("/autocomplete", response_model=List[dict])
def autocomplete_company(name: str = Query(..., description="Company name to search")):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Google API key not configured")

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": name,
        "types": "establishment",
        "key": GOOGLE_API_KEY
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Error fetching autocomplete from Google API")

    data = response.json()
    suggestions = [
        {"description": pred.get("description"), "place_id": pred.get("place_id")}
        for pred in data.get("predictions", [])
    ]
    return suggestions

# --- Fetch full company details by Google Place ID ---
@router.get("/details", response_model=dict)
def get_company_details(place_id: str = Query(..., description="Google Place ID of the company")):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Google API key not configured")

    url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&key={GOOGLE_API_KEY}"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Error fetching details from Google API")

    result = resp.json().get("result", {})
    # Extract useful fields
    company_details = {
        "name": result.get("name"),
        "address": result.get("formatted_address"),
        "phone": result.get("formatted_phone_number"),
        "website": result.get("website")
    }
    return company_details
