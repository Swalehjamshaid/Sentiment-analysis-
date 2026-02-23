# FILE: app/routes/companies.py
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import requests
import logging
import os
from ..db import get_db
from ..models import Company
from ..schemas import CompanyCreate, CompanyResponse  # assuming you have these in schemas.py

router = APIRouter(prefix="/api/companies", tags=["companies"])

# ─────────────────────────────────────────────────────────────
# Config & Logger
# ─────────────────────────────────────────────────────────────
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
API_TOKEN = os.getenv("API_TOKEN")  # Optional server-side auth for POST

logger = logging.getLogger("companies")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

_G_TIMEOUT = (5, 10)  # connect / read timeout in seconds


def _extract_city_from_components(components: List[Dict[str, Any]]) -> Optional[str]:
    """
    Returns best-effort city from Google address components.
    Prefers 'locality' → 'postal_town' → 'administrative_area_level_2'
    """
    for comp in components or []:
        types = comp.get("types", [])
        if "locality" in types:
            return comp.get("long_name")
        if "postal_town" in types:
            return comp.get("long_name")
        if "administrative_area_level_2" in types:
            return comp.get("long_name")
    return None


def _google_place_details(place_id: str, language: Optional[str] = None) -> Dict[str, Any]:
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    fields = [
        "name", "formatted_address", "formatted_phone_number", "website",
        "address_components", "geometry", "international_phone_number",
        "rating", "user_ratings_total", "url"
    ]
    params = {
        "place_id": place_id,
        "fields": ",".join(fields),
        "key": GOOGLE_PLACES_API_KEY,
    }
    if language:
        params["language"] = language

    try:
        resp = requests.get(url, params=params, timeout=_G_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("status") not in ("OK", "ZERO_RESULTS"):
            raise ValueError(f"Google status: {payload.get('status')}")
        return payload.get("result", {}) or {}
    except Exception as e:
        logger.warning(f"Google Place Details failed for {place_id}: {e}")
        raise HTTPException(502, f"Google Places error: {str(e)}")


# ─────────────────────────────────────────────────────────────
# 1. GET /api/companies - List with search, pagination, sort, filter
# ─────────────────────────────────────────────────────────────
@router.get("/", response_model=List[CompanyResponse])
def get_companies(
    search: Optional[str] = Query(None, description="Search in name/city/address"),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=5, le=200),
    status: Optional[str] = Query("active", description="Filter by status"),
    sort: str = Query("name", regex="^(name|city|created_at)$"),
    order: str = Query("asc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    query = db.query(Company)

    if status:
        query = query.filter(Company.status == status)

    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            (Company.name.ilike(s)) |
            (Company.city.ilike(s)) |
            (Company.address.ilike(s))
        )

    # Sorting
    sort_col = getattr(Company, sort)
    query = query.order_by(sort_col.desc() if order == "desc" else sort_col)

    # Pagination
    offset = (page - 1) * limit
    companies = query.offset(offset).limit(limit).all()

    return companies


# ─────────────────────────────────────────────────────────────
# 2. POST /api/companies - Create company (with Google enrichment)
# ─────────────────────────────────────────────────────────────
@router.post("/", response_model=CompanyResponse, status_code=201)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    language: Optional[str] = Query(None, description="Google response language (e.g. en, ur, ar)"),
):
    # Optional token validation
    if API_TOKEN:
        token = (x_api_key or "").strip()
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if token != API_TOKEN:
            raise HTTPException(401, "Invalid API token")

    # Duplicate checks
    if payload.place_id:
        if db.query(Company).filter(Company.place_id == payload.place_id).first():
            raise HTTPException(409, "Place ID already registered")

    # Secondary check (name + city)
    if payload.name and payload.city:
        dup = db.query(Company).filter(
            Company.name.ilike(payload.name),
            Company.city.ilike(payload.city)
        ).first()
        if dup:
            raise HTTPException(409, "Company with same name & city already exists")

    # Start with payload values
    name = payload.name
    city = payload.city
    address = payload.address
    phone = payload.phone
    website = payload.website
    lat = payload.lat
    lng = payload.lng
    email = payload.email
    description = payload.description

    # Enrich from Google if place_id provided
    if payload.place_id and GOOGLE_PLACES_API_KEY:
        result = _google_place_details(payload.place_id, language=language)
        name = result.get("name", name)
        address = result.get("formatted_address") or address
        phone = result.get("formatted_phone_number") or result.get("international_phone_number") or phone
        website = result.get("website") or website
        city = _extract_city_from_components(result.get("address_components", [])) or city
        loc = (result.get("geometry") or {}).get("location") or {}
        lat = loc.get("lat", lat)
        lng = loc.get("lng", lng)

    new_company = Company(
        name=name,
        place_id=payload.place_id,
        city=city,
        lat=lat,
        lng=lng,
        email=email,
        phone=phone,
        address=address,
        website=website,
        description=description,
        status="active",
        created_at=datetime.now(timezone.utc),
    )

    db.add(new_company)
    db.commit()
    db.refresh(new_company)

    return new_company


# ─────────────────────────────────────────────────────────────
# 3. GET /api/companies/autocomplete - Google Places Autocomplete
# ─────────────────────────────────────────────────────────────
@router.get("/autocomplete", response_model=List[Dict[str, str]])
def autocomplete(
    q: str = Query(..., min_length=2),
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    radius: Optional[int] = Query(50000, ge=1000, le=100000),
    language: Optional[str] = Query(None),
):
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")

    params = {
        "input": q,
        "types": "establishment",
        "key": GOOGLE_PLACES_API_KEY,
    }
    if lat is not None and lng is not None:
        params["location"] = f"{lat},{lng}"
        params["radius"] = radius
    if language:
        params["language"] = language

    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/autocomplete/json",
            params=params,
            timeout=_G_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "OK":
            raise ValueError(data.get("status"))
        return [
            {"description": p.get("description"), "place_id": p.get("place_id")}
            for p in data.get("predictions", [])
        ]
    except Exception as e:
        logger.warning(f"Autocomplete failed: {e}")
        raise HTTPException(502, f"Google Autocomplete error: {str(e)}")


# ─────────────────────────────────────────────────────────────
# 4. GET /api/companies/details/{place_id} - Preview place before create
# ─────────────────────────────────────────────────────────────
@router.get("/details/{place_id}", response_model=Dict[str, Any])
def get_place_details(
    place_id: str,
    language: Optional[str] = Query(None),
):
    result = _google_place_details(place_id, language=language)

    loc = (result.get("geometry") or {}).get("location") or {}

    return {
        "name": result.get("name"),
        "address": result.get("formatted_address"),
        "phone": result.get("formatted_phone_number") or result.get("international_phone_number"),
        "website": result.get("website"),
        "city": _extract_city_from_components(result.get("address_components", [])),
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
        "rating": result.get("rating"),
        "total_ratings": result.get("user_ratings_total"),
        "url": result.get("url"),
    }
