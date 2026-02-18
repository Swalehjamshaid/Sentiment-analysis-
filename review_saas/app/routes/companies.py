# Filename: app/routes/companies.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
import requests
from datetime import datetime
import os

from ..db import get_db
from ..models import Company, User

router = APIRouter(prefix="/companies", tags=["companies"])

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# -----------------------------
# List all companies
# -----------------------------
@router.get("/", response_model=List[dict])
def list_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "city": c.city,
            "status": c.status,
            "lat": c.lat,
            "lng": c.lng,
            "place_id": c.place_id
        }
        for c in companies
    ]

# -----------------------------
# Add a new company
# -----------------------------
@router.post("/")
def add_company(
    name: str = Query(...),
    city: str = Query(None),
    place_id: str = Query(None),
    lat: float = Query(None),
    lng: float = Query(None),
    db: Session = Depends(get_db)
):
    # Fetch details from Google if place_id is provided and lat/lng not given
    if place_id and (lat is None or lng is None or not city):
        url = (
            f"https://maps.googleapis.com/maps/api/place/details/json"
            f"?place_id={place_id}"
            f"&fields=name,formatted_address,formatted_phone_number,website,address_components,geometry"
            f"&key={GOOGLE_API_KEY}"
        )
        resp = requests.get(url)
        if resp.status_code == 200:
            data = resp.json().get("result", {})
            name = data.get("name", name)
            geometry = data.get("geometry", {}).get("location", {})
            lat = lat or geometry.get("lat")
            lng = lng or geometry.get("lng")
            if not city:
                for comp in data.get("address_components", []):
                    if "locality" in comp.get("types", []):
                        city = comp.get("long_name")
                        break
        else:
            raise HTTPException(status_code=502, detail="Failed to fetch details from Google API")

    # Save company
    new_company = Company(
        name=name,
        city=city,
        place_id=place_id,
        lat=lat,
        lng=lng,
        status="active",
        owner_id=1  # Replace with current user ID if auth is implemented
    )
    db.add(new_company)
    db.commit()
    db.refresh(new_company)

    return {
        "id": new_company.id,
        "name": new_company.name,
        "city": new_company.city,
        "status": new_company.status,
        "lat": new_company.lat,
        "lng": new_company.lng,
        "place_id": new_company.place_id
    }

# -----------------------------
# Google Autocomplete
# -----------------------------
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

# -----------------------------
# Google Place Details
# -----------------------------
@router.get("/details", response_model=dict)
def get_company_details(place_id: str = Query(..., description="Google Place ID of the company")):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Google API key not configured")

    url = (
        f"https://maps.googleapis.com/maps/api/place/details/json"
        f"?place_id={place_id}"
        f"&fields=name,formatted_address,formatted_phone_number,website,address_components,geometry"
        f"&key={GOOGLE_API_KEY}"
    )

    resp = requests.get(url)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Error fetching details from Google API")

    result = resp.json().get("result", {})

    company_details = {
        "name": result.get("name"),
        "address": result.get("formatted_address"),
        "phone": result.get("formatted_phone_number"),
        "website": result.get("website")
    }

    # Extract city
    city = None
    for comp in result.get("address_components", []):
        if "locality" in comp.get("types", []):
            city = comp.get("long_name")
            break
    company_details["city"] = city

    geometry = result.get("geometry", {}).get("location", {})
    company_details["lat"] = geometry.get("lat")
    company_details["lng"] = geometry.get("lng")

    return company_details
