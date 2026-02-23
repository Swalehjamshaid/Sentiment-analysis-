# FILE: app/routes/companies.py

from __future__ import annotations

import os
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Path
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..db import get_db
from ..models import Company
from ..schemas import CompanyCreate, CompanyResponse

router = APIRouter(prefix="/api/companies", tags=["companies"])

# ─────────────────────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────────────────────
logger = logging.getLogger("companies")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
GOOGLE_BUSINESS_API_KEY = os.getenv("GOOGLE_BUSINESS_API_KEY")
API_TOKEN = os.getenv("API_TOKEN")
_G_TIMEOUT: Tuple[int, int] = (5, 15)

# Only allow safe sortable fields
ALLOWED_SORT_FIELDS = {
    "id": Company.id,
    "name": Company.name,
    "city": Company.city,
    "created_at": Company.created_at,
    "status": Company.status,
}

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _extract_city(components: List[Dict[str, Any]]) -> Optional[str]:
    for comp in components or []:
        types = comp.get("types", [])
        if "locality" in types or "postal_town" in types:
            return comp.get("long_name")
    return None

# ─────────────────────────────────────────────────────────────
# Google Places API
# ─────────────────────────────────────────────────────────────
def _google_place_details(place_id: str, language: Optional[str] = None) -> Dict[str, Any]:
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    fields = (
        "name,formatted_address,address_components,geometry,"
        "website,international_phone_number,rating,"
        "user_ratings_total,url"
    )

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
        if status == "ZERO_RESULTS":
            return {}
        if status != "OK":
            logger.warning(f"Google Places status: {status}")
            raise HTTPException(502, f"Google status: {status}")

        return payload.get("result", {}) or {}
    except requests.RequestException as e:
        logger.error(f"Google request failed: {e}")
        raise HTTPException(502, "Google Places request failed")

# ─────────────────────────────────────────────────────────────
# Google Business Profile API
# ─────────────────────────────────────────────────────────────
def _google_business_locations() -> Dict[str, Any]:
    """
    Fetch all locations from Google Business Profile API using API key.
    Note: OAuth token flow is recommended for full features.
    """
    if not GOOGLE_BUSINESS_API_KEY:
        raise HTTPException(503, "Google Business API key not configured")

    url = "https://mybusinessbusinessinformation.googleapis.com/v1/accounts"
    headers = {
        "Authorization": f"Bearer {GOOGLE_BUSINESS_API_KEY}"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=_G_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"Google Business API request failed: {e}")
        raise HTTPException(502, "Google Business API request failed")

# ─────────────────────────────────────────────────────────────
# Token Validation
# ─────────────────────────────────────────────────────────────
def _validate_token(x_api_key: Optional[str], authorization: Optional[str]):
    if not API_TOKEN:
        return

    token = (x_api_key or "").strip()
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token != API_TOKEN:
        raise HTTPException(401, "Invalid API token")

# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@router.get("/", response_model=List[CompanyResponse])
def list_companies(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=5, le=200),
    sort: str = Query("created_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    query = db.query(Company)

    if status:
        query = query.filter(Company.status == status)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Company.name.ilike(term),
                Company.city.ilike(term),
                Company.address.ilike(term),
            )
        )

    sort_column = ALLOWED_SORT_FIELDS.get(sort)
    if sort_column is not None:
        query = query.order_by(
            sort_column.asc() if order == "asc" else sort_column.desc()
        )

    total_offset = (page - 1) * limit
    return query.offset(total_offset).limit(limit).all()


@router.post("/", response_model=CompanyResponse, status_code=201)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    language: Optional[str] = Query(None),
):
    _validate_token(x_api_key, authorization)

    if payload.place_id:
        existing = db.query(Company).filter(Company.place_id == payload.place_id).first()
        if existing:
            raise HTTPException(409, "Place already registered")

    name = payload.name
    city = payload.city
    address = payload.address
    website = payload.website
    phone = payload.phone
    lat = payload.lat
    lng = payload.lng

    if payload.place_id:
        result = _google_place_details(payload.place_id, language)
        name = result.get("name", name)
        address = result.get("formatted_address", address)
        website = result.get("website", website)
        phone = result.get("international_phone_number", phone)
        city = _extract_city(result.get("address_components")) or city
        loc = (result.get("geometry") or {}).get("location") or {}
        lat = loc.get("lat", lat)
        lng = loc.get("lng", lng)

    new_company = Company(
        name=name,
        place_id=payload.place_id,
        city=city,
        address=address,
        phone=phone,
        website=website,
        email=payload.email,
        lat=lat,
        lng=lng,
        description=payload.description,
        status="active",
        created_at=datetime.now(timezone.utc),
    )

    db.add(new_company)
    db.commit()
    db.refresh(new_company)
    return new_company

@router.get("/autocomplete")
def autocomplete_company(
    q: str = Query(..., min_length=2),
    language: Optional[str] = Query(None),
):
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": q,
        "types": "establishment",
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
            logger.warning(f"Autocomplete status: {status}")
            raise HTTPException(502, f"Google status: {status}")

        return [
            {
                "description": p["description"],
                "place_id": p["place_id"],
            }
            for p in payload.get("predictions", [])
        ]
    except requests.RequestException as e:
        logger.error(f"Autocomplete failed: {e}")
        raise HTTPException(502, "Google Autocomplete failed")


@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(
    company_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    return company

# ─────────────────────────────────────────────────────────────
# NEW ROUTE: Google Business API
# ─────────────────────────────────────────────────────────────
@router.get("/google/business")
def get_google_business_info():
    """
    Fetch all accounts/locations from Google Business Profile API
    """
    return _google_business_locations()
