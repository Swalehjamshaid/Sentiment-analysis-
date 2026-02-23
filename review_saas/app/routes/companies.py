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
# Config (env-first; fallback to the keys you provided)
# ─────────────────────────────────────────────────────────────
# NOTE: For production, prefer environment variables and secret managers.
GOOGLE_MAPS_API_KEY = os.getenv(
    "GOOGLE_MAPS_API_KEY",
    "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg"
)
GOOGLE_PLACES_API_KEY = os.getenv(
    "GOOGLE_PLACES_API_KEY",
    "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg"
)
GOOGLE_BUSINESS_API_KEY = os.getenv(
    "GOOGLE_BUSINESS_API_KEY",
    "AIzaSyDjQFzX3Wak4maUWhSXstPmnbBOOKGVGfc"
)
API_TOKEN = os.getenv("API_TOKEN")  # Optional server-side auth for POST

_G_TIMEOUT: Tuple[int, int] = (5, 15)  # (connect, read) seconds

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
def _extract_city(components: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """
    Returns best-effort city from Google address components.
    Prefers 'locality'; falls back to 'postal_town', admin level 2/1.
    """
    for comp in components or []:
        types = comp.get("types", [])
        if "locality" in types or "postal_town" in types:
            return comp.get("long_name")
    # fallback pass
    for comp in components or []:
        types = comp.get("types", [])
        if "administrative_area_level_2" in types or "administrative_area_level_1" in types:
            return comp.get("long_name")
    return None


def _validate_token(x_api_key: Optional[str], authorization: Optional[str]) -> None:
    """Optional token validation if API_TOKEN is provided."""
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
    key = GOOGLE_PLACES_API_KEY or GOOGLE_MAPS_API_KEY
    if not key:
        raise HTTPException(503, "Google Places API not configured")

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    fields = (
        "name,formatted_address,address_components,geometry,"
        "website,international_phone_number,formatted_phone_number,"
        "rating,user_ratings_total,url"
    )
    params = {
        "place_id": place_id,
        "fields": fields,
        "key": key,
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
            logger.warning(f"Google Places status for {place_id}: {status}")
            raise HTTPException(502, f"Google Places status: {status}")
        return payload.get("result", {}) or {}
    except requests.RequestException as e:
        logger.error(f"Google Places request failed: {e}")
        raise HTTPException(502, "Google Places request failed")


def _google_places_autocomplete(q: str, language: Optional[str] = None) -> List[Dict[str, str]]:
    key = GOOGLE_PLACES_API_KEY or GOOGLE_MAPS_API_KEY
    if not key:
        raise HTTPException(503, "Google Places API not configured")

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": q,
        "types": "establishment",
        "key": key,
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
            {"description": p.get("description", ""), "place_id": p.get("place_id", "")}
            for p in payload.get("predictions", [])
        ]
    except requests.RequestException as e:
        logger.error(f"Autocomplete failed: {e}")
        raise HTTPException(502, "Google Autocomplete failed")


# ─────────────────────────────────────────────────────────────
# Google Business Profile API (OAuth strongly recommended)
# We attempt a KEY-based call and fail gracefully with guidance.
# ─────────────────────────────────────────────────────────────
def _google_business_accounts() -> Dict[str, Any]:
    """
    Attempts to list GBP accounts. The Business Profile APIs require OAuth 2.0.
    Using an API key alone typically returns 401/403. We catch and return a
    structured message so the route remains error-free.
    Docs: https://developers.google.com/my-business/
    """
    # Attempt with API key as query param (will likely 401/403 without OAuth)
    url = "https://mybusinessbusinessinformation.googleapis.com/v1/accounts"
    params = {}
    if GOOGLE_BUSINESS_API_KEY:
        params["key"] = GOOGLE_BUSINESS_API_KEY

    try:
        resp = requests.get(url, params=params, timeout=_G_TIMEOUT)
        if resp.status_code in (401, 403):
            # Graceful message: API reachable but requires OAuth
            return {
                "ok": False,
                "message": "Google Business Profile API requires OAuth 2.0 access token.",
                "hint": "Use a Google OAuth client and pass Authorization: Bearer <access_token>.",
                "status_code": resp.status_code,
                "details": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
            }
        resp.raise_for_status()
        return {"ok": True, "data": resp.json()}
    except requests.RequestException as e:
        logger.error(f"Google Business API request failed: {e}")
        return {
            "ok": False,
            "message": "Google Business API request failed",
            "error": str(e),
        }


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────
@router.get("/", response_model=List[CompanyResponse])
def list_companies(
    search: Optional[str] = Query(None, description="Search by name/city/address"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(30, ge=5, le=200, description="Items per page"),
    sort: str = Query("created_at", description=f"One of: {', '.join(ALLOWED_SORT_FIELDS.keys())}"),
    order: str = Query("desc", regex="^(asc|desc)$", description="Sort direction"),
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

    offset = (page - 1) * limit
    companies = query.offset(offset).limit(limit).all()
    return companies


@router.post("/", response_model=CompanyResponse, status_code=201)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    language: Optional[str] = Query(None, description="Google response language (e.g. en, ur, ar)"),
):
    _validate_token(x_api_key, authorization)

    # Duplicates
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

    # Start from provided values
    name = payload.name
    city = payload.city
    address = payload.address
    website = getattr(payload, "website", None)
    phone = payload.phone
    lat = payload.lat
    lng = payload.lng

    # Enrich from Google Places
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
):
    return _google_places_autocomplete(q=q, language=language)


@router.get("/details/{place_id}", response_model=Dict[str, Any])
def place_details(
    place_id: str,
    language: Optional[str] = Query(None, description="Language code"),
):
    result = _google_place_details(place_id, language)
    loc = (result.get("geometry") or {}).get("location") or {}
    return {
        "name": result.get("name"),
        "address": result.get("formatted_address"),
        "city": _extract_city(result.get("address_components")),
        "phone": result.get("formatted_phone_number") or result.get("international_phone_number"),
        "website": result.get("website"),
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
        "rating": result.get("rating"),
        "user_ratings_total": result.get("user_ratings_total"),
        "url": result.get("url"),
    }


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
# Google Business Profile info (graceful; requires OAuth for real data)
# ─────────────────────────────────────────────────────────────
@router.get("/google/business")
def get_google_business_info():
    """
    Fetch accounts from Google Business Profile API.
    This endpoint remains error-free even when OAuth isn't configured,
    returning an informative payload instead of a server error.
    """
    return _google_business_accounts()
