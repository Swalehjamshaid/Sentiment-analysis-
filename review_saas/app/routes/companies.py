# FILE: app/routes/companies.py

from __future__ import annotations

import os
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Path
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

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
# Config (env first, then fallback to provided constants)
# ─────────────────────────────────────────────────────────────
# Provided constants (fallbacks)
_DEFAULT_GOOGLE_MAPS_API_KEY = "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg"
_DEFAULT_GOOGLE_PLACES_API_KEY = "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg"
_DEFAULT_GOOGLE_BUSINESS_API_KEY = "AIzaSyDjQFzX3Wak4maUWhSXstPmnbBOOKGVGfc"  # NOTE: API key is NOT valid for GBP OAuth

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", _DEFAULT_GOOGLE_MAPS_API_KEY)
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", _DEFAULT_GOOGLE_PLACES_API_KEY)

# For Google Business Profile, you must provide an OAuth access token
# via GBP_ACCESS_TOKEN (env) or Authorization: Bearer <token>.
GBP_ACCESS_TOKEN = os.getenv("GBP_ACCESS_TOKEN")  # preferred
GOOGLE_BUSINESS_API_KEY = os.getenv("GOOGLE_BUSINESS_API_KEY", _DEFAULT_GOOGLE_BUSINESS_API_KEY)  # informational only

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
        if "administrative_area_level_2" in types:
            return comp.get("long_name")
    return None

def _validate_token(x_api_key: Optional[str], authorization: Optional[str]):
    """Optional server-side token gate for create endpoint."""
    if not API_TOKEN:
        return
    token = (x_api_key or "").strip()
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token != API_TOKEN:
        raise HTTPException(401, "Invalid API token")

# ─────────────────────────────────────────────────────────────
# Google Places API
# ─────────────────────────────────────────────────────────────
def _google_place_details(place_id: str, language: Optional[str] = None) -> Dict[str, Any]:
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    fields = (
        "name,formatted_address,address_components,geometry,"
        "website,formatted_phone_number,international_phone_number,rating,"
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
            raise HTTPException(502, f"Google Places status: {status}")

        return payload.get("result", {}) or {}
    except requests.RequestException as e:
        logger.error(f"Places details failed: {e}")
        raise HTTPException(502, "Google Places request failed")

# ─────────────────────────────────────────────────────────────
# Google Business Profile API (requires OAuth access token)
# ─────────────────────────────────────────────────────────────
def _gbp_request(path: str, access_token: Optional[str]) -> Dict[str, Any]:
    """Call GBP Business Information API with OAuth token. API keys won't work."""
    token = (access_token or GBP_ACCESS_TOKEN)
    if not token:
        # Return helpful, non-throwing payload so UI can render a note
        raise HTTPException(
            501,
            "Google Business Profile requires OAuth access token. "
            "Set GBP_ACCESS_TOKEN env or pass Authorization: Bearer <token>."
        )
    url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{path.lstrip('/')}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=_G_TIMEOUT)
        if resp.status_code == 401:
            raise HTTPException(401, "GBP token invalid or expired")
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"GBP request failed: {e}")
        raise HTTPException(502, "Google Business Profile request failed")

# ─────────────────────────────────────────────────────────────
# Health / Config
# ─────────────────────────────────────────────────────────────
@router.get("/health")
def health():
    """Quick health check for API key wiring (never returns the keys)."""
    return {
        "ok": True,
        "google_places_configured": bool(GOOGLE_PLACES_API_KEY),
        "google_maps_configured": bool(GOOGLE_MAPS_API_KEY),
        "gbp_oauth_configured": bool(GBP_ACCESS_TOKEN),
    }

# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────
@router.get("/", response_model=List[CompanyResponse])
def list_companies(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query("active", description="Filter by status (default active)"),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=5, le=200),
    sort: str = Query("created_at"),
    order: str = Query("desc", regex=r"^(asc|desc)$"),
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

    sort_column = ALLOWED_SORT_FIELDS.get(sort, Company.created_at)
    query = query.order_by(sort_column.asc() if order == "asc" else sort_column.desc())

    total_offset = (page - 1) * limit
    return query.offset(total_offset).limit(limit).all()

@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(
    company_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    return company

@router.post("/", response_model=CompanyResponse, status_code=201)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    language: Optional[str] = Query(None),
):
    _validate_token(x_api_key, authorization)

    # Duplicate checks
    if payload.place_id:
        existing = db.query(Company).filter(Company.place_id == payload.place_id).first()
        if existing:
            raise HTTPException(409, "Place already registered")

    if payload.name and payload.city:
        dup = db.query(Company).filter(
            Company.name.ilike(payload.name),
            Company.city.ilike(payload.city),
        ).first()
        if dup:
            raise HTTPException(409, "Company with same name & city already exists")

    # Seed with payload
    name = payload.name
    city = payload.city
    address = payload.address
    website = payload.website
    phone = payload.phone
    lat = payload.lat
    lng = payload.lng
    maps_link = None

    # Enrich via Google Places
    if payload.place_id:
        result = _google_place_details(payload.place_id, language)
        name = result.get("name", name)
        address = result.get("formatted_address", address)
        website = result.get("website", website)
        phone = result.get("formatted_phone_number") or result.get("international_phone_number") or phone
        city = _extract_city(result.get("address_components")) or city
        loc = (result.get("geometry") or {}).get("location") or {}
        lat = loc.get("lat", lat)
        lng = loc.get("lng", lng)
        maps_link = result.get("url")

    new_company = Company(
        name=name,
        place_id=payload.place_id,
        maps_link=maps_link,
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
            raise HTTPException(502, f"Google Places status: {status}")

        return [
            {
                "description": p.get("description"),
                "place_id": p.get("place_id"),
            }
            for p in payload.get("predictions", [])
        ]
    except requests.RequestException as e:
        logger.error(f"Autocomplete failed: {e}")
        raise HTTPException(502, "Google Autocomplete failed")

@router.get("/details/{place_id}")
def details_by_place_id(
    place_id: str,
    language: Optional[str] = Query(None),
):
    result = _google_place_details(place_id, language)
    loc = (result.get("geometry") or {}).get("location") or {}
    return {
        "name": result.get("name"),
        "address": result.get("formatted_address"),
        "phone": result.get("formatted_phone_number") or result.get("international_phone_number"),
        "website": result.get("website"),
        "city": _extract_city(result.get("address_components", [])),
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
        "rating": result.get("rating"),
        "user_ratings_total": result.get("user_ratings_total"),
        "url": result.get("url"),
    }

# ─────────────────────────────────────────────────────────────
# Optional: Dashboard helper endpoints
# ─────────────────────────────────────────────────────────────
@router.get("/summary")
def companies_summary(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    base_q = db.query(Company)
    if status:
        base_q = base_q.filter(Company.status == status)
    total = db.query(func.count(Company.id)).scalar() or 0
    active = db.query(func.count(Company.id)).filter(Company.status == "active").scalar() or 0
    inactive = db.query(func.count(Company.id)).filter(Company.status == "inactive").scalar() or 0
    cities = db.query(func.count(func.distinct(Company.city))).scalar() or 0
    last_created = db.query(func.max(Company.created_at)).scalar()
    return {
        "total": int(total),
        "active": int(active),
        "inactive": int(inactive),
        "cities": int(cities),
        "last_created_at": last_created.isoformat() if last_created else None,
    }

@router.get("/stats")
def companies_stats(
    top_cities: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Company.city, func.count(Company.id))
          .group_by(Company.city)
          .order_by(func.count(Company.id)).all()
    )
    rows = sorted(rows, key=lambda x: x[1], reverse=True)[:top_cities]
    return [{"city": c or "(Unknown)", "count": int(n)} for c, n in rows]

@router.get("/datatable")
def companies_datatable(
    draw: int = Query(1, ge=0),
    start: int = Query(0, ge=0),
    length: int = Query(25, ge=1, le=500),
    search_value: Optional[str] = Query(None, alias="search[value]"),
    order_col_idx: Optional[int] = Query(None, alias="order[0][column]"),
    order_dir: Optional[str] = Query("asc", alias="order[0][dir]", regex=r"^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    columns = ["name", "city", "address", "created_at", "status"]
    order_by_col = columns[order_col_idx] if (order_col_idx is not None and 0 <= order_col_idx < len(columns)) else "name"

    q = db.query(Company)
    total = db.query(func.count(Company.id)).scalar() or 0

    if search_value:
        s = f"%{search_value.strip()}%"
        q = q.filter(or_(Company.name.ilike(s), Company.city.ilike(s), Company.address.ilike(s)))

    records_filtered = q.with_entities(func.count(Company.id)).scalar() or 0

    ob = getattr(Company, order_by_col)
    q = q.order_by(ob.desc() if order_dir == "desc" else ob.asc())
    data_rows = q.offset(start).limit(length).all()

    def _to_dict(c: Company) -> Dict[str, Any]:
        return {
            "id": c.id,
            "name": c.name,
            "city": c.city,
            "address": c.address,
            "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "lat": c.lat,
            "lng": c.lng,
        }
    return {
        "draw": draw,
        "recordsTotal": int(total),
        "recordsFiltered": int(records_filtered),
        "data": [_to_dict(x) for x in data_rows],
    }

@router.get("/markers")
def companies_markers(
    limit: int = Query(1000, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    q = db.query(Company).filter(Company.lat.isnot(None), Company.lng.isnot(None))
    rows = q.order_by(Company.created_at.desc()).limit(limit).all()
    return [
        {"id": c.id, "name": c.name, "city": c.city, "lat": c.lat, "lng": c.lng, "status": c.status}
        for c in rows
    ]

# ─────────────────────────────────────────────────────────────
# Google Business routes (safe, OAuth-aware)
# ─────────────────────────────────────────────────────────────
@router.get("/google/business/accounts")
def gbp_accounts(authorization: Optional[str] = Header(None, alias="Authorization")):
    """
    Requires OAuth token. If you only have an API key, this will return 501 with guidance.
    """
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    return _gbp_request("accounts", access_token=token)

@router.get("/google/business/locations")
def gbp_locations(
    account: str = Query(..., description="Account resource name, e.g. accounts/123456789"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    path = f"{account}/locations"
    return _gbp_request(path, access_token=token)
