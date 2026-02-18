# Filename: app/routes/companies.py

from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Company
from typing import List
import requests
from datetime import datetime
import os

router = APIRouter(prefix="/companies", tags=["companies"])
templates = Jinja2Templates(directory="app/templates")

# Separate API Keys
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")      # Frontend
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")  # Backend


# ─────────────────────────────────────────────
# Render HTML template with Google Maps JS key
# ─────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
def companies_page(request: Request):
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(status_code=500, detail="Google Maps API key not configured")

    return templates.TemplateResponse(
        "companies.html",
        {
            "request": request,
            "google_maps_api_key": GOOGLE_MAPS_API_KEY
        }
    )


# ─────────────────────────────────────────────
# List all companies
# ─────────────────────────────────────────────
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


# ─────────────────────────────────────────────
# Add Company
# ─────────────────────────────────────────────
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
    # Fetch enriched details from Google Places API (Backend Key)
    if place_id:
        if not GOOGLE_PLACES_API_KEY:
            raise HTTPException(status_code=500, detail="Google Places API key not configured")

        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            "place_id": place_id,
            "fields": "name,formatted_address,formatted_phone_number,address_components,geometry",
            "key": GOOGLE_PLACES_API_KEY
        }

        resp = requests.get(url, params=params)

        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to fetch details from Google API")

        result = resp.json().get("result", {})

        name = result.get("name", name)
        phone = result.get("formatted_phone_number", phone)
        address = result.get("formatted_address", address)

        # Extract city
        for comp in result.get("address_components", []):
            if "locality" in comp.get("types", []):
                city = comp.get("long_name")
                break

        geometry = result.get("geometry", {}).get("location", {})
        lat = geometry.get("lat", lat)
        lng = geometry.get("lng", lng)

    # Save to DB
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


# ─────────────────────────────────────────────
# Google Places Autocomplete (Backend Key)
# ─────────────────────────────────────────────
@router.get("/autocomplete", response_model=List[dict])
def autocomplete_company(name: str):

    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(status_code=500, detail="Google Places API key not configured")

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": name,
        "types": "establishment",
        "key": GOOGLE_PLACES_API_KEY
    }

    response = requests.get(url, params=params)

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Error fetching autocomplete from Google API")

    data = response.json()

    return [
        {
            "description": pred.get("description"),
            "place_id": pred.get("place_id")
        }
        for pred in data.get("predictions", [])
    ]


# ─────────────────────────────────────────────
# Get Full Company Details (Backend Key)
# ─────────────────────────────────────────────
@router.get("/details", response_model=dict)
def get_company_details(place_id: str):

    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(status_code=500, detail="Google Places API key not configured")

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,formatted_phone_number,address_components,geometry",
        "key": GOOGLE_PLACES_API_KEY
    }

    resp = requests.get(url, params=params)

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Error fetching details from Google API")

    result = resp.json().get("result", {})

    company_details = {
        "name": result.get("name"),
        "address": result.get("formatted_address"),
        "phone": result.get("formatted_phone_number"),
        "city": None
    }

    for comp in result.get("address_components", []):
        if "locality" in comp.get("types", []):
            company_details["city"] = comp.get("long_name")
            break

    geometry = result.get("geometry", {}).get("location", {})
    company_details["lat"] = geometry.get("lat")
    company_details["lng"] = geometry.get("lng")

    return company_details
