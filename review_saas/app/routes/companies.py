from fastapi import APIRouter, Depends, HTTPException, Query, Header, Path
from sqlalchemy.orm import Session, defer
from sqlalchemy import func, or_
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
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
API_TOKEN = os.getenv("API_TOKEN")

logger = logging.getLogger("companies")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

_G_TIMEOUT: Tuple[int, int] = (5, 15)


# ─────────────────────────────────────────────────────────────
# Google Helpers
# ─────────────────────────────────────────────────────────────
def _extract_city_from_components(components: List[Dict[str, Any]]) -> Optional[str]:
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
    fields = (
        "name,formatted_address,formatted_phone_number,"
        "website,address_components,geometry,"
        "international_phone_number,rating,user_ratings_total,url"
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
            logger.warning(f"Google Places error: {status}")
            raise HTTPException(502, f"Google Places status: {status}")

        return payload.get("result", {}) or {}

    except requests.RequestException as e:
        logger.error(f"Google Places request failed: {e}")
        raise HTTPException(502, "Google Places request failed")


# ─────────────────────────────────────────────────────────────
# LIST COMPANIES
# ─────────────────────────────────────────────────────────────
@router.get("/", response_model=List[CompanyResponse])
def get_companies(
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=5, le=200),
    status: Optional[str] = Query(None),
    sort: str = Query("name"),
    order: str = Query("asc"),
    db: Session = Depends(get_db),
):
    query = db.query(Company)

    if status:
        query = query.filter(Company.status == status)

    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Company.name.ilike(s),
                Company.city.ilike(s),
                Company.address.ilike(s),
            )
        )

    # Defensive sort
    if hasattr(Company, sort):
        sort_col = getattr(Company, sort)
        query = query.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    offset = (page - 1) * limit
    return query.offset(offset).limit(limit).all()


# ─────────────────────────────────────────────────────────────
# CREATE COMPANY
# ─────────────────────────────────────────────────────────────
@router.post("/", response_model=CompanyResponse, status_code=201)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    language: Optional[str] = Query(None),
):
    # Optional API token validation
    if API_TOKEN:
        token = (x_api_key or "").strip()
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if token != API_TOKEN:
            raise HTTPException(401, "Invalid API token")

    if payload.place_id:
        existing = db.query(Company).filter(Company.place_id == payload.place_id).first()
        if existing:
            raise HTTPException(409, "Place already registered")

    name = payload.name
    city = payload.city
    address = payload.address
    phone = payload.phone
    website = payload.website
    lat = payload.lat
    lng = payload.lng

    if payload.place_id:
        result = _google_place_details(payload.place_id, language)
        name = result.get("name", name)
        address = result.get("formatted_address", address)
        phone = result.get("formatted_phone_number") or result.get("international_phone_number") or phone
        website = result.get("website", website)
        city = _extract_city_from_components(result.get("address_components")) or city

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


# ─────────────────────────────────────────────────────────────
# AUTOCOMPLETE
# ─────────────────────────────────────────────────────────────
@router.get("/autocomplete")
def autocomplete_company(
    q: str = Query(..., min_length=2),
    language: Optional[str] = Query(None),
):
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")

    params = {
        "input": q,
        "types": "establishment",
        "key": GOOGLE_PLACES_API_KEY,
    }

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
            raise HTTPException(502, f"Google status: {data.get('status')}")

        return [
            {"description": p["description"], "place_id": p["place_id"]}
            for p in data.get("predictions", [])
        ]

    except Exception as e:
        logger.error(f"Autocomplete error: {e}")
        raise HTTPException(502, "Google Autocomplete failed")


# ─────────────────────────────────────────────────────────────
# GET COMPANY BY ID
# ─────────────────────────────────────────────────────────────
@router.get("/{company_id}", response_model=CompanyResponse)
def get_company_by_id(
    company_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    return company
