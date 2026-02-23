# FILE: app/routes/companies.py

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import requests
import os
import logging

from ..db import get_db
from ..models import Company
from ..schemas import CompanyCreate, CompanyResponse

router = APIRouter(prefix="/api/companies", tags=["companies"])

# ─────────────────────────────────────────────────────────────
# Config & Logger
# ─────────────────────────────────────────────────────────────
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
API_TOKEN = os.getenv("API_TOKEN")  # Optional server-side auth for POST

logger = logging.getLogger("companies")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

# Small helper to call Google endpoints with a consistent timeout
_G_TIMEOUT = (5, 10)  # (connect, read) seconds


def _extract_city_from_components(components: List[Dict[str, Any]]) -> Optional[str]:
    """
    Returns best-effort city from Google address components.
    Prefers 'locality'; falls back to 'postal_town' or admin level 2.
    """
    city = None
    for comp in components or []:
        types = comp.get("types", [])
        if "locality" in types:
            return comp.get("long_name")
        if "postal_town" in types:
            city = city or comp.get("long_name")
        if "administrative_area_level_2" in types:
            city = city or comp.get("long_name")
    return city


def _google_place_details(place_id: str, language: Optional[str] = None) -> Dict[str, Any]:
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    fields = ",".join([
        "name",
        "formatted_address",
        "formatted_phone_number",
        "website",
        "address_components",
        "geometry",
        "international_phone_number",
        "rating",
        "user_ratings_total",
        "url"
    ])
    params = {
        "place_id": place_id,
        "fields": fields,
        "key": GOOGLE_PLACES_API_KEY,
    }
    if language:
        params["language"] = language

    try:
        resp = requests.get(url, params=params, timeout=_G_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        status = payload.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            raise HTTPException(502, f"Places Details error: {status}")
        return payload.get("result", {}) or {}
    except requests.RequestException as e:
        logger.warning(f"Places Details request failed: {e}")
        raise HTTPException(502, f"Google Places error: {str(e)}")


# ─────────────────────────────────────────────────────────────
# 1️⃣ GET COMPANIES (supports search & pagination for dashboard scroll)
#    - /api/companies?search=&page=1&limit=30&status=active&sort=name&order=asc
# ─────────────────────────────────────────────────────────────
@router.get("/", response_model=List[CompanyResponse])
def get_companies(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None, min_length=1),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=200),
    status: Optional[str] = Query("active"),
    sort: str = Query("name", pattern="^(name|city|created_at)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
):
    q = db.query(Company)
    if status:
        q = q.filter(Company.status == status)

    if search:
        s = f"%{search.strip()}%"
        # Adjust fields as per your model
        q = q.filter(
            (Company.name.ilike(s)) |
            (Company.city.ilike(s)) |
            (Company.address.ilike(s))
        )

    # Sorting
    sort_col = getattr(Company, sort)
    if order == "desc":
        sort_col = sort_col.desc()
    q = q.order_by(sort_col)

    # Pagination
    offset = (page - 1) * limit
    companies = q.offset(offset).limit(limit).all()
    return companies


# ─────────────────────────────────────────────────────────────
# 2️⃣ ADD COMPANY (from Google autofill)
#     - Optional token guard via API_TOKEN using either:
#       X-API-Key header or Authorization: Bearer <token>
# ─────────────────────────────────────────────────────────────
@router.post("/", response_model=CompanyResponse, status_code=201)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    language: Optional[str] = Query(None, description="ISO language for Google details, e.g., en, ur, ar"),
):
    # Optional API token check (if configured)
    if API_TOKEN:
        token = (x_api_key or "").strip()
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if token != API_TOKEN:
            raise HTTPException(401, "Invalid API token")

    # Duplicate by place_id
    if payload.place_id:
        existing = db.query(Company).filter(Company.place_id == payload.place_id).first()
        if existing:
            raise HTTPException(409, "Company already exists with this Place ID")

    # Defaults from payload
    name = payload.name
    address = payload.address
    phone = payload.phone
    website = getattr(payload, "website", None)
    city = payload.city
    lat = payload.lat
    lng = payload.lng

    # Enrich using Google Places Details if place_id provided
    if payload.place_id and GOOGLE_PLACES_API_KEY:
        result = _google_place_details(payload.place_id, language=language)
        name = result.get("name", name)
        address = result.get("formatted_address") or address
        phone = result.get("formatted_phone_number") or result.get("international_phone_number") or phone
        website = result.get("website") or website

        # City extraction
        city = _extract_city_from_components(result.get("address_components", [])) or city

        # Coordinates
        loc = (result.get("geometry") or {}).get("location") or {}
        lat = loc.get("lat", lat)
        lng = loc.get("lng", lng)

    # Secondary duplicate guard by (name + city) if present
    if name and city:
        dup = db.query(Company).filter(
            Company.name.ilike(name),
            Company.city.ilike(city)
        ).first()
        if dup:
            raise HTTPException(409, "Company with same name & city already exists")

    new_company = Company(
        name=name,
        place_id=payload.place_id,
        city=city,
        lat=lat,
        lng=lng,
        email=payload.email,
        phone=phone,
        address=address,
        website=website,
        description=payload.description,
        status="active",
        created_at=datetime.now(timezone.utc),
    )

    db.add(new_company)
    db.commit()
    db.refresh(new_company)
    return new_company


# ─────────────────────────────────────────────────────────────
# 3️⃣ GOOGLE AUTOCOMPLETE (for search box)
#     - Optional location bias: lat, lng, radius (meters)
#     - Optional language code
# ─────────────────────────────────────────────────────────────
@router.get("/autocomplete", response_model=List[Dict[str, str]])
def autocomplete_company(
    q: str = Query(..., min_length=2),
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    radius: Optional[int] = Query(50000, ge=1, le=50000),
    language: Optional[str] = Query(None),
):
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params: Dict[str, Any] = {
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
        response = requests.get(url, params=params, timeout=_G_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        logger.warning(f"Places Autocomplete failed: {e}")
        raise HTTPException(502, f"Google Autocomplete error: {str(e)}")

    return [
        {
            "description": p.get("description"),
            "place_id": p.get("place_id"),
        }
        for p in data.get("predictions", [])
    ]


# ─────────────────────────────────────────────────────────────
# 4️⃣ OPTIONAL: Get Place Details before creating (handy for UI preview)
#     /api/companies/details/{place_id}?language=en
# ─────────────────────────────────────────────────────────────
@router.get("/details/{place_id}", response_model=Dict[str, Any])
def google_details(place_id: str, language: Optional[str] = Query(None)):
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")
    result = _google_place_details(place_id, language=language)
    # Return a trimmed payload suitable for your form autofill
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
        "user_ratings_total": result.get("user_ratings_total"),
        "url": result.get("url"),
    }
