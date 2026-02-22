# FILE: app/routes/companies.py
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from ..db import get_db
from ..models import Company
import requests
import logging
from datetime import datetime
import os

router = APIRouter(prefix="/companies", tags=["companies"])

templates = Jinja2Templates(directory="app/templates")

logger = logging.getLogger("companies")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ────────────────────────────────────────────── Config ─────
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")  # for frontend JS

if not GOOGLE_PLACES_API_KEY:
    logger.warning("GOOGLE_PLACES_API_KEY is missing – Google Places endpoints will fail")

# ────────────────────────────────────────────── Models ─────
class CompanyCreate(BaseModel):
    name: str
    place_id: str
    city: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None  # e.g. "Lahore, Pakistan"

class CompanyOut(BaseModel):
    id: int
    name: str
    city: Optional[str]
    status: Optional[str]
    place_id: Optional[str]
    lat: Optional[float] = None
    lng: Optional[float] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None

# ────────────────────────────────────────────── Routes ─────

@router.get("/", response_class=HTMLResponse, name="companies_page")
async def companies_page(request: Request):
    """
    Render the companies management page (if you have a separate companies.html template).
    Injects the Maps JS API key for client-side autocomplete.
    """
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(500, "Google Maps JavaScript API key not configured for frontend")

    return templates.TemplateResponse(
        "companies.html",
        {
            "request": request,
            "google_maps_api_key": GOOGLE_MAPS_API_KEY,
        }
    )


@router.get("/list", response_model=List[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    """
    Returns a safe list of companies (only existing columns).
    Defer unused/problematic columns to avoid errors.
    """
    companies = (
        db.query(Company)
        .options(
            # Defer any columns that might not exist yet or cause issues
            *[defer(getattr(Company, col)) for col in [
                "lat", "lng", "owner_id", "email", "phone", "address", "description"
            ] if hasattr(Company, col)]
        )
        .all()
    )

    return [
        CompanyOut(
            id=c.id,
            name=c.name,
            city=getattr(c, "city", None),
            status=getattr(c, "status", "active"),
            place_id=getattr(c, "place_id", None),
            lat=None,
            lng=None,
            email=None,
            phone=None,
            address=None,
            description=None,
        )
        for c in companies
    ]


@router.post("/", response_model=CompanyOut, status_code=201)
def add_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """
    Create a new company (JSON body).
    Enriches with Google Places if place_id provided.
    """
    # Optional API token check (if configured)
    if os.getenv("API_TOKEN") and x_api_key != os.getenv("API_TOKEN"):
        raise HTTPException(401, "Invalid API token")

    if db.query(Company).filter(Company.name.ilike(payload.name)).first():
        raise HTTPException(409, "Company with this name already exists")
    if db.query(Company).filter(Company.place_id == payload.place_id).first():
        raise HTTPException(409, "This Google Place ID is already registered")

    name = payload.name
    city = payload.city
    lat = lng = phone = address = None

    # Enrich from Google Places if place_id given
    if payload.place_id and GOOGLE_PLACES_API_KEY:
        try:
            url = "https://maps.googleapis.com/maps/api/place/details/json"
            params = {
                "place_id": payload.place_id,
                "fields": "name,formatted_address,formatted_phone_number,address_components,geometry",
                "key": GOOGLE_PLACES_API_KEY,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            result = resp.json().get("result", {})

            name = result.get("name", name)
            address = result.get("formatted_address")
            phone = result.get("formatted_phone_number")

            # Extract city
            for comp in result.get("address_components", []):
                if "locality" in comp.get("types", []):
                    city = comp.get("long_name")
                    break

            loc = result.get("geometry", {}).get("location", {})
            lat = loc.get("lat")
            lng = loc.get("lng")

        except requests.RequestException as e:
            logger.error(f"Google Places enrichment failed: {e}")
            # Continue anyway – don't fail creation

    new_company = Company(
        name=name,
        place_id=payload.place_id,
        city=city,
        status="active",
        created_at=datetime.utcnow(),
        # Optional fields – only set if model has them
        **({"website": payload.website} if hasattr(Company, "website") and payload.website else {}),
        **({"location": payload.location} if hasattr(Company, "location") and payload.location else {}),
        # lat/lng/phone/address – uncomment when columns exist
        # lat=lat, lng=lng, phone=phone, address=address,
    )

    db.add(new_company)
    db.commit()
    db.refresh(new_company)

    return CompanyOut(
        id=new_company.id,
        name=new_company.name,
        city=getattr(new_company, "city", None),
        status=getattr(new_company, "status", "active"),
        place_id=getattr(new_company, "place_id", None),
        lat=None,
        lng=None,
        email=None,
        phone=None,
        address=None,
        description=None,
    )


@router.get("/autocomplete", response_model=List[Dict[str, str]])
def autocomplete_company(q: str = Query(..., min_length=2)):
    """
    Google Places Autocomplete – for frontend search.
    """
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")

    try:
        url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
        params = {
            "input": q,
            "types": "establishment",
            "key": GOOGLE_PLACES_API_KEY,
        }
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()

        return [
            {"description": p.get("description"), "place_id": p.get("place_id")}
            for p in data.get("predictions", [])
        ]
    except requests.RequestException as e:
        logger.error(f"Places autocomplete failed: {e}")
        raise HTTPException(502, "Failed to reach Google Places API")


@router.get("/details", response_model=Dict[str, Any])
def get_company_details(place_id: str = Query(...)):
    """
    Fetch full details for a Google Place ID (used by frontend or internal calls).
    """
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")

    try:
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            "place_id": place_id,
            "fields": "name,formatted_address,formatted_phone_number,address_components,geometry",
            "key": GOOGLE_PLACES_API_KEY,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        result = resp.json().get("result", {})

        city = None
        for comp in result.get("address_components", []):
            if "locality" in comp.get("types", []):
                city = comp.get("long_name")
                break

        loc = result.get("geometry", {}).get("location", {})

        return {
            "name": result.get("name"),
            "formatted_address": result.get("formatted_address"),
            "phone": result.get("formatted_phone_number"),
            "city": city,
            "lat": loc.get("lat"),
            "lng": loc.get("lng"),
            "place_id": place_id,
        }
    except requests.RequestException as e:
        logger.error(f"Place details failed for {place_id}: {e}")
        raise HTTPException(502, "Failed to fetch place details")
