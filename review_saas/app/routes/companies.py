# Filename: app/routes/companies.py

from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Company
from typing import List
import requests
from datetime import datetime
import os

router = APIRouter(prefix="/companies", tags=["companies"])

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# --- List all companies ---
@router.get("/list", response_model=List[dict])
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
            "email": getattr(c, "email", None),
            "phone": getattr(c, "phone", None),
            "address": getattr(c, "address", None),
            "description": getattr(c, "description", None)
        }
        for c in companies
    ]

# --- Add a new company via HTML form or Google Place ID ---
@router.post("/")
def add_company(
    name: str = Form(...),
    city: str = Form(None),
    place_id: str = Form(None),
    lat: float = Form(None),
    lng: float = Form(None),
    email: str = Form(None),
    phone: str = Form(None),
    address: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    # Fetch details from Google API if place_id provided
    if place_id:
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
            if "address_components" in data:
                for comp in data["address_components"]:
                    if "locality" in comp.get("types", []):
                        city = comp.get("long_name")
                        break
            geometry = data.get("geometry", {}).get("location", {})
            lat = geometry.get("lat", lat)
            lng = geometry.get("lng", lng)
            phone = data.get("formatted_phone_number", phone)
            address = data.get("formatted_address", address)
        else:
            raise HTTPException(status_code=502, detail="Failed to fetch details from Google API")

    # Save all fields to the database
    new_company = Company(
        name=name,
        city=city,
        lat=lat,
        lng=lng,
        status="active",
        place_id=place_id,
        email=email,
        phone=phone,
        address=address,
        description=description,
        created_at=datetime.utcnow()
    )
    db.add(new_company)
    db.commit()
    db.refresh(new_company)

    return {
        "id": new_company.id,
        "name": new_company.name,
        "city": new_company.city,
        "lat": new_company.lat,
        "lng": new_company.lng,
        "email": new_company.email,
        "phone": new_company.phone,
        "address": new_company.address,
        "description": new_company.description,
        "status": new_company.status
    }

# --- Autocomplete companies using Google Places API ---
@router.get("/autocomplete", response_model=List[dict])
def autocomplete_company(name: str):
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
    return [
        {"description": pred.get("description"), "place_id": pred.get("place_id")}
        for pred in data.get("predictions", [])
    ]

# --- Fetch full company details by Google Place ID ---
@router.get("/details", response_model=dict)
def get_company_details(place_id: str):
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
