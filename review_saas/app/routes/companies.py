from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, defer
from ..db import get_db
from ..models import Company
from typing import List
import requests
from datetime import datetime
import os

router = APIRouter(prefix="/companies", tags=["companies"])
templates = Jinja2Templates(directory="app/templates")

# Google API Keys
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

if not GOOGLE_MAPS_API_KEY or not GOOGLE_PLACES_API_KEY:
    print("⚠️ Google API keys missing or not loaded!")
else:
    print("✅ Google API keys loaded successfully.")


# Render HTML template
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


# List all companies – skip ALL currently missing/problematic columns
@router.get("/list", response_model=List[dict])
def list_companies(db: Session = Depends(get_db)):
    companies = (
        db.query(Company)
        .options(
            defer(Company.lat),         # skip lat
            defer(Company.lng),         # skip lng
            defer(Company.owner_id),    # skip owner_id
            defer(Company.email),       # skip email ← fixes current error
            defer(Company.phone),       # skip phone
            defer(Company.address),     # skip address
            defer(Company.description), # skip description
        )
        .all()
    )
    return [
        {
            "id": c.id,
            "name": c.name,
            "city": getattr(c, "city", None),
            "status": getattr(c, "status", None),
            "lat": None,          # skipped → return None
            "lng": None,
            "email": None,
            "phone": None,
            "address": None,
            "description": None
        }
        for c in companies
    ]


# Add company – keep only safe columns to avoid INSERT error
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
    # Enrich from Google Places
    if place_id:
        if not GOOGLE_PLACES_API_KEY:
            raise HTTPException(status_code=500, detail="Google Places API key not configured")

        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            "place_id": place_id,
            "fields": "name,formatted_address,formatted_phone_number,address_components,geometry",
            "key": GOOGLE_PLACES_API_KEY
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"⚠️ Google Places API error: {e}")
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

    # Save to DB – only using columns that likely exist to avoid crash
    new_company = Company(
        name=name,
        city=city,
        status="active",
        place_id=place_id,
        created_at=datetime.utcnow()
        # Temporarily skipped: lat, lng, email, phone, address, description, owner_id
        # Uncomment when columns are added in database
        # lat=lat,
        # lng=lng,
        # email=email,
        # phone=phone,
        # address=address,
        # description=description,
        # owner_id=None  # or current_user.id if authenticated
    )

    db.add(new_company)
    db.commit()
    db.refresh(new_company)

    # Return same structure (missing fields as None)
    return {
        "id": new_company.id,
        "name": new_company.name,
        "city": new_company.city,
        "lat": None,
        "lng": None,
        "email": None,
        "phone": None,
        "address": None,
        "description": None,
        "status": new_company.status
    }


# Google Places Autocomplete – unchanged
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

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"⚠️ Google Autocomplete API error: {e}")
        raise HTTPException(status_code=502, detail="Error fetching autocomplete from Google API")

    data = response.json()

    return [
        {
            "description": pred.get("description"),
            "place_id": pred.get("place_id")
        }
        for pred in data.get("predictions", [])
    ]


# Get full company details – unchanged
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

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"⚠️ Google Place Details API error: {e}")
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
