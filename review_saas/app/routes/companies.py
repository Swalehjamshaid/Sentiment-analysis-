# FILE: app/routes/companies.py
from __future__ import annotations

import os
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Path
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

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
# Config (env override; fallback to provided constants)
# ─────────────────────────────────────────────────────────────
_DEFAULT_GOOGLE_MAPS_API_KEY = "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg"
_DEFAULT_GOOGLE_PLACES_API_KEY = "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg"
_DEFAULT_GOOGLE_BUSINESS_API_KEY = "AIzaSyDjQFzX3Wak4maUWhSXstPmnbBOOKGVGfc"

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", _DEFAULT_GOOGLE_MAPS_API_KEY)
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", _DEFAULT_GOOGLE_PLACES_API_KEY)
GOOGLE_BUSINESS_API_KEY = os.getenv("GOOGLE_BUSINESS_API_KEY", _DEFAULT_GOOGLE_BUSINESS_API_KEY)
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
    """Optional API token guard for mutating routes."""
    if not API_TOKEN:
        return
    token = (x_api_key or "").strip()
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token != API_TOKEN:
        raise HTTPException(401, "Invalid API token")

# ─────────────────────────────────────────────────────────────
# Google Places API helpers
# ─────────────────────────────────────────────────────────────
def _google_place_details(place_id: str, language: Optional[str] = None) -> Dict[str, Any]:
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    fields = ",".join([
        "name", "formatted_address", "address_components", "geometry",
        "website", "international_phone_number", "formatted_phone_number",
        "rating", "user_ratings_total", "url", "place_id"
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
        if status == "ZERO_RESULTS":
            return {}
        if status != "OK":
            logger.warning(f"Google Places status: {status}")
            raise HTTPException(502, f"Google Places status: {status}")

        return payload.get("result", {}) or {}
    except requests.RequestException as e:
        logger.error(f"Google Places request failed: {e}")
        raise HTTPException(502, "Google Places request failed")

def _google_places_autocomplete(
    q: str,
    language: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius: Optional[int] = None,
) -> List[Dict[str, str]]:
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params: Dict[str, Any] = {
        "input": q,
        "types": "establishment",
        "key": GOOGLE_PLACES_API_KEY,
    }
    if language:
        params["language"] = language
    if lat is not None and lng is not None:
        params["location"] = f"{lat},{lng}"
        if radius:
            params["radius"] = int(radius)

    try:
        resp = requests.get(url, params=params, timeout=_G_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        status = payload.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            logger.warning(f"Autocomplete status: {status}")
            raise HTTPException(502, f"Google Places status: {status}")

        return [
            {"description": p.get("description", ""), "place_id": p.get("place_id", "")}
            for p in payload.get("predictions", [])
        ]
    except requests.RequestException as e:
        logger.error(f"Autocomplete failed: {e}")
        raise HTTPException(502, "Google Autocomplete failed")

# ─────────────────────────────────────────────────────────────
# Google Maps helpers (Static / Embed)
# ─────────────────────────────────────────────────────────────
def _static_map_url(
    lat: float,
    lng: float,
    zoom: int = 14,
    width: int = 640,
    height: int = 320,
    marker_label: str = "C",
) -> str:
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(503, "Google Maps API not configured")
    base = "https://maps.googleapis.com/maps/api/staticmap"
    center = f"{lat},{lng}"
    marker = f"color:red|label:{marker_label}|{center}"
    size = f"{width}x{height}"
    return (
        f"{base}?center={center}&zoom={zoom}&size={size}&markers={marker}&key={GOOGLE_MAPS_API_KEY}"
    )

def _embed_map_url(
    place_id: Optional[str] = None,
    query: Optional[str] = None,
    zoom: Optional[int] = None,
) -> str:
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(503, "Google Maps API not configured")
    base = "https://www.google.com/maps/embed/v1"
    if place_id:
        url = f"{base}/place?key={GOOGLE_MAPS_API_KEY}&q=place_id:{place_id}"
        if zoom is not None:
            url += f"&zoom={zoom}"
        return url
    q = (query or "").strip()
    if not q:
        raise HTTPException(400, "Either place_id or query is required")
    url = f"{base}/search?key={GOOGLE_MAPS_API_KEY}&q={requests.utils.quote(q)}"
    if zoom is not None:
        url += f"&zoom={zoom}"
    return url

# ─────────────────────────────────────────────────────────────
# Google Business Profile API (guarded – generally requires OAuth)
# ─────────────────────────────────────────────────────────────
def _google_business_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Attempt a GBP request. Most endpoints require OAuth.
    We include API key for best-effort; handle 401/403 gracefully.
    """
    if not GOOGLE_BUSINESS_API_KEY:
        raise HTTPException(503, "Google Business API key not configured")

    base = "https://mybusinessbusinessinformation.googleapis.com/v1"
    url = f"{base}/{path.lstrip('/')}"
    # Some Google services accept API key as `key` param; GBP typically needs OAuth.
    params = dict(params or {})
    params.setdefault("key", GOOGLE_BUSINESS_API_KEY)

    try:
        resp = requests.get(url, params=params, timeout=_G_TIMEOUT)
        # If OAuth is missing, GBP usually returns 401/403 with JSON error.
        if resp.status_code in (401, 403):
            detail = resp.json().get("error", {}).get("message", "Unauthorized")
            logger.warning(f"GBP auth error: {detail}")
            raise HTTPException(
                status_code=501,
                detail="Google Business Profile API requires OAuth 2.0 for this endpoint. "
                       "Provide an OAuth access token or integrate a service account."
            )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"Google Business API request failed: {e}")
        raise HTTPException(502, "Google Business API request failed")

# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@router.get("/", response_model=List[CompanyResponse])
def list_companies(
    search: Optional[str] = Query(None, description="Search on name, city, address"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(30, ge=5, le=200, description="Items per page"),
    sort: str = Query("created_at", description="Sort field"),
    order: str = Query("desc", regex=r"^(asc|desc)$", description="Sort direction"),
    db: Session = Depends(get_db),
):
    query = db.query(Company)

    if status:
        query = query.filter(Company.status == status)

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(Company.name.ilike(term), Company.city.ilike(term), Company.address.ilike(term))
        )

    sort_column = ALLOWED_SORT_FIELDS.get(sort, Company.created_at)
    query = query.order_by(sort_column.asc() if order == "asc" else sort_column.desc())

    total_offset = (page - 1) * limit
    return query.offset(total_offset).limit(limit).all()

@router.post("/", response_model=CompanyResponse, status_code=201)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    language: Optional[str] = Query(None, description="Places language (e.g., en, ur)"),
):
    _validate_token(x_api_key, authorization)

    # Duplicate checks
    if payload.place_id:
        existing = db.query(Company).filter(Company.place_id == payload.place_id).first()
        if existing:
            raise HTTPException(409, "Place already registered")

    if payload.name and payload.city:
        dup = (
            db.query(Company)
            .filter(Company.name.ilike(payload.name), Company.city.ilike(payload.city))
            .first()
        )
        if dup:
            raise HTTPException(409, "Company with same name & city already exists")

    # Start with provided values
    name = payload.name
    city = payload.city
    address = payload.address
    website = payload.website
    phone = payload.phone
    lat = payload.lat
    lng = payload.lng

    # Enrich with Places Details if place_id provided
    if payload.place_id:
        result = _google_place_details(payload.place_id, language)
        name = result.get("name", name)
        address = result.get("formatted_address", address)
        website = result.get("website", website)
        phone = (
            result.get("formatted_phone_number")
            or result.get("international_phone_number")
            or phone
        )
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
    q: str = Query(..., min_length=2, description="Search term"),
    language: Optional[str] = Query(None, description="Language code"),
    lat: Optional[float] = Query(None, description="Latitude (bias)"),
    lng: Optional[float] = Query(None, description="Longitude (bias)"),
    radius: Optional[int] = Query(50000, ge=1000, le=100000, description="Radius in meters"),
):
    return _google_places_autocomplete(q=q, language=language, lat=lat, lng=lng, radius=radius)

@router.get("/details/{place_id}", response_model=Dict[str, Any])
def google_details(
    place_id: str,
    language: Optional[str] = Query(None, description="Places language"),
):
    result = _google_place_details(place_id, language=language)
    loc = (result.get("geometry") or {}).get("location") or {}
    return {
        "place_id": result.get("place_id") or place_id,
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

@router.get("/markers", response_model=List[Dict[str, Any]])
def companies_markers(
    status: Optional[str] = Query(None, description="Status filter"),
    min_lat: Optional[float] = Query(None, description="Min latitude"),
    min_lng: Optional[float] = Query(None, description="Min longitude"),
    max_lat: Optional[float] = Query(None, description="Max latitude"),
    max_lng: Optional[float] = Query(None, description="Max longitude"),
    limit: int = Query(1000, ge=1, le=10000, description="Max markers"),
    db: Session = Depends(get_db),
):
    q = db.query(Company)
    if status:
        q = q.filter(Company.status == status)
    if hasattr(Company, "lat") and hasattr(Company, "lng"):
        q = q.filter(Company.lat.isnot(None), Company.lng.isnot(None))
        if None not in (min_lat, min_lng, max_lat, max_lng):
            q = q.filter(
                Company.lat >= min_lat,
                Company.lat <= max_lat,
                Company.lng >= min_lng,
                Company.lng <= max_lng,
            )
    rows = q.order_by(Company.created_at.desc()).limit(limit).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "city": c.city,
            "status": c.status,
            "lat": c.lat,
            "lng": c.lng,
        }
        for c in rows
    ]

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
# Maps utilities (Static / Embed)
# ─────────────────────────────────────────────────────────────
@router.get("/maps/static", response_model=Dict[str, str])
def google_maps_static(
    lat: float = Query(...),
    lng: float = Query(...),
    zoom: int = Query(14, ge=0, le=21),
    width: int = Query(640, ge=64, le=2048),
    height: int = Query(320, ge=64, le=2048),
    marker_label: str = Query("C", min_length=1, max_length=2),
):
    url = _static_map_url(lat=lat, lng=lng, zoom=zoom, width=width, height=height, marker_label=marker_label)
    return {"url": url}

@router.get("/maps/embed", response_model=Dict[str, str])
def google_maps_embed(
    place_id: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    zoom: Optional[int] = Query(None, ge=0, le=21),
):
    url = _embed_map_url(place_id=place_id, query=query, zoom=zoom)
    return {"url": url}

# ─────────────────────────────────────────────────────────────
# Google Business Profile (guarded)
# ─────────────────────────────────────────────────────────────
@router.get("/google/business/accounts", response_model=Dict[str, Any])
def gbp_accounts():
    """
    Note: GBP Accounts typically require OAuth 2.0.
    This returns 501 with guidance if OAuth is not configured.
    """
    # Common list endpoint (OAuth required). Keep for wiring completeness.
    return _google_business_get("accounts")

@router.get("/google/business/locations", response_model=Dict[str, Any])
def gbp_locations(
    account: Optional[str] = Query(None, description="Account resource name e.g. accounts/123456789"),
    page_size: int = Query(50, ge=1, le=200),
    page_token: Optional[str] = Query(None),
):
    """
    List locations for a GBP account. Requires OAuth; returns guidance if missing.
    """
    if not account:
        # Some GBP endpoints support search; but generally also need OAuth.
        params = {"readMask": "name,title,storeCode,languageCode,metadata", "pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return _google_business_get("locations", params=params)
    else:
        path = f"{account}/locations"
        params = {"readMask": "name,title,storeCode,languageCode,metadata", "pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return _google_business_get(path, params=params)
