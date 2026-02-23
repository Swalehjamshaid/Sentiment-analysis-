# FILE: review_saas/app/routes/companies.py

from __future__ import annotations

import os
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Path, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..db import get_db
from ..models import Company, Review
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
# Config (ENV → fallback to provided keys)
# ─────────────────────────────────────────────────────────────
GOOGLE_MAPS_API_KEY: str = os.getenv(
    "GOOGLE_MAPS_API_KEY",
    "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg",
)
GOOGLE_PLACES_API_KEY: str = os.getenv(
    "GOOGLE_PLACES_API_KEY",
    "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg",
)
GOOGLE_BUSINESS_API_KEY: str = os.getenv(
    "GOOGLE_BUSINESS_API_KEY",
    "AIzaSyDjQFzX3Wak4maUWhSXstPmnbBOOKGVGfc",
)
API_TOKEN = os.getenv("API_TOKEN")

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
def _validate_token(x_api_key: Optional[str], authorization: Optional[str]) -> None:
    """Optional API token guard (if API_TOKEN set)."""
    if not API_TOKEN:
        return
    token = (x_api_key or "").strip()
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token != API_TOKEN:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API token")


def _extract_city(components: List[Dict[str, Any]]) -> Optional[str]:
    for comp in components or []:
        types = comp.get("types", [])
        if "locality" in types or "postal_town" in types:
            return comp.get("long_name")
        if "administrative_area_level_2" in types:
            return comp.get("long_name")
    return None


def _epoch_to_utc(ts: Optional[int]) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except Exception:
        return None


def _sentiment_from_rating(r: Optional[float]) -> str:
    if r is None or r == 3:
        return "Neutral"
    return "Positive" if r >= 4 else "Negative"


# ─────────────────────────────────────────────────────────────
# Google Places API Wrappers
# ─────────────────────────────────────────────────────────────
def _google_place_details(
    place_id: str,
    language: Optional[str] = None,
    include_reviews: bool = False,
) -> Dict[str, Any]:
    """
    Fetch Place Details. When include_reviews=True, also request 'reviews' field (max 5).
    """
    api_key = GOOGLE_PLACES_API_KEY or GOOGLE_MAPS_API_KEY
    if not api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google Places API not configured")

    url = "https://maps.googleapis.com/maps/api/place/details/json"

    fields = [
        "name", "formatted_address", "address_components", "geometry",
        "website", "international_phone_number", "rating", "user_ratings_total", "url"
    ]
    if include_reviews:
        fields.append("reviews")

    params = {
        "place_id": place_id,
        "fields": ",".join(fields),
        "key": api_key,
    }
    if language:
        params["language"] = language

    try:
        resp = requests.get(url, params=params, timeout=_G_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        status_text = payload.get("status")
        if status_text == "ZERO_RESULTS":
            return {}
        if status_text != "OK":
            logger.warning(f"Places Details status={status_text} error={payload.get('error_message')}")
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Google Places status: {status_text}")
        return payload.get("result", {}) or {}
    except requests.RequestException as e:
        logger.error(f"Google Places request failed: {e}")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Google Places request failed")


def _google_places_autocomplete(q: str, language: Optional[str] = None) -> List[Dict[str, str]]:
    api_key = GOOGLE_PLACES_API_KEY or GOOGLE_MAPS_API_KEY
    if not api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google Places API not configured")

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params: Dict[str, Any] = {"input": q, "types": "establishment", "key": api_key}
    if language:
        params["language"] = language

    try:
        resp = requests.get(url, params=params, timeout=_G_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        status_text = payload.get("status")
        if status_text not in ("OK", "ZERO_RESULTS"):
            logger.warning(f"Autocomplete status={status_text} error={payload.get('error_message')}")
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Google Places status: {status_text}")
        return [
            {"description": p.get("description"), "place_id": p.get("place_id")}
            for p in payload.get("predictions", [])
        ]
    except requests.RequestException as e:
        logger.error(f"Autocomplete failed: {e}")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Google Autocomplete failed")


def _google_place_reviews(place_id: str, language: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return up to 5 reviews embedded in Place Details."""
    result = _google_place_details(place_id, language=language, include_reviews=True)
    return result.get("reviews", []) or []


# ─────────────────────────────────────────────────────────────
# Google Business Profile API (informational placeholder)
# NOTE: Real GBP access requires OAuth 2.0. This endpoint returns a helpful
# message if using API key in Authorization to avoid breaking your UI.
# ─────────────────────────────────────────────────────────────
def _google_business_accounts() -> Dict[str, Any]:
    if not GOOGLE_BUSINESS_API_KEY:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google Business API key not configured")

    url = "https://mybusinessbusinessinformation.googleapis.com/v1/accounts"
    headers = {"Authorization": f"Bearer {GOOGLE_BUSINESS_API_KEY}"}
    try:
        resp = requests.get(url, headers=headers, timeout=_G_TIMEOUT)
        if resp.status_code in (401, 403):
            return {
                "ok": False,
                "message": "Google Business Profile API requires OAuth 2.0; API key is not sufficient.",
                "status_code": resp.status_code,
                "body": resp.text,
            }
        resp.raise_for_status()
        return {"ok": True, "data": resp.json()}
    except requests.RequestException as e:
        logger.warning(f"GBP call failed: {e}")
        return {"ok": False, "message": "Failed to reach Google Business Profile API", "error": str(e)}


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@router.get("/", response_model=List[CompanyResponse])
def list_companies(
    search: Optional[str] = Query(None, description="Search name, city, address"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=5, le=200),
    sort: str = Query("created_at", description="id|name|city|created_at|status"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    """
    Paginated companies list for dashboard tables (search + sort + filter).
    """
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
        query = query.order_by(sort_column.asc() if order == "asc" else sort_column.desc())

    total_offset = (page - 1) * limit
    rows = query.offset(total_offset).limit(limit).all()
    return rows


@router.post("/", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    language: Optional[str] = Query(None),
):
    """
    Create a company. If 'place_id' is supplied, enrich with Google Places Details.
    """
    _validate_token(x_api_key, authorization)

    if payload.place_id:
        existing = db.query(Company).filter(Company.place_id == payload.place_id).first()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, "Place already registered")

    name = payload.name
    city = payload.city
    address = payload.address
    website = payload.website
    phone = payload.phone
    lat = payload.lat
    lng = payload.lng
    maps_link = None

    if payload.place_id:
        result = _google_place_details(payload.place_id, language=language)
        name = result.get("name", name)
        address = result.get("formatted_address", address)
        website = result.get("website", website)
        phone = result.get("international_phone_number", phone)
        city = _extract_city(result.get("address_components") or []) or city
        loc = (result.get("geometry") or {}).get("location") or {}
        lat = loc.get("lat", lat)
        lng = loc.get("lng", lng)
        maps_link = result.get("url")

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
        maps_link=maps_link,
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    db.add(new_company)
    db.commit()
    db.refresh(new_company)
    return new_company


@router.delete("/{company_id}")
def delete_company(
    company_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """
    Delete a company and cascade-delete its reviews (as per model relationship).
    """
    _validate_token(x_api_key, authorization)
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    db.delete(company)
    db.commit()
    return {"ok": True, "deleted_id": company_id}


@router.get("/autocomplete")
def autocomplete_company(
    q: str = Query(..., min_length=2, description="Free-text: establishment name/address"),
    language: Optional[str] = Query(None),
):
    """
    Google Places Autocomplete for establishments (used by dashboard 'Add Company' flow).
    """
    return _google_places_autocomplete(q=q, language=language)


@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(
    company_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return company


# ─────────────────────────────────────────────────────────────
# Reviews utilities for a company (import & list)
# ─────────────────────────────────────────────────────────────
@router.post("/{company_id}/reviews/sync")
def sync_company_reviews(
    company_id: int = Path(..., ge=1),
    language: Optional[str] = Query(None, description="e.g., en, ur"),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """
    Pull up to 5 latest reviews via Google Places Details and upsert into DB.
    NOTE: Place Details exposes only a sample of recent reviews.
    """
    _validate_token(x_api_key, authorization)

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    if not company.place_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Company has no place_id configured")

    reviews = _google_place_reviews(company.place_id, language=language)

    created = 0
    updated = 0

    for rv in reviews:
        # Compose a stable external_id
        ext_id = f"gplace:{company.place_id}:{rv.get('author_name','unknown')}:{rv.get('time')}"
        existing = (
            db.query(Review)
            .filter(Review.company_id == company_id, Review.external_id == ext_id)
            .first()
        )

        rating = rv.get("rating")
        text = rv.get("text") or None
        reviewer_name = rv.get("author_name") or None
        reviewer_avatar = rv.get("profile_photo_url") or None
        review_date = _epoch_to_utc(rv.get("time"))
        lang = rv.get("language") or None

        sent_label = _sentiment_from_rating(float(rating) if rating is not None else None)
        sent_score = 0.0
        if sent_label == "Positive":
            sent_score = 0.7
        elif sent_label == "Negative":
            sent_score = -0.7

        if existing:
            existing.text = text
            existing.rating = rating
            existing.reviewer_name = reviewer_name
            existing.reviewer_avatar = reviewer_avatar
            existing.review_date = review_date
            existing.language = lang
            existing.sentiment_category = sent_label
            existing.sentiment_score = sent_score
            updated += 1
        else:
            row = Review(
                company_id=company_id,
                external_id=ext_id,
                text=text,
                rating=rating,
                review_date=review_date,
                reviewer_name=reviewer_name,
                reviewer_avatar=reviewer_avatar,
                sentiment_category=sent_label,
                sentiment_score=sent_score,
                keywords=None,
                language=lang,
                fetch_status="Success",
            )
            db.add(row)
            created += 1

    db.commit()
    return {"ok": True, "created": created, "updated": updated, "fetched": len(reviews)}


@router.get("/{company_id}/reviews")
def list_company_reviews(
    company_id: int = Path(..., ge=1),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    Simple paginated review list for a company (ops/debug).
    """
    q = db.query(Review).filter(Review.company_id == company_id)
    total = q.count()
    rows = (
        q.order_by(Review.review_date.desc().nullslast())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    def to_dict(r: Review) -> Dict[str, Any]:
        return {
            "id": r.id,
            "external_id": r.external_id,
            "review_date": r.review_date.isoformat() if r.review_date else None,
            "rating": r.rating,
            "text": r.text,
            "reviewer_name": r.reviewer_name,
            "reviewer_avatar": r.reviewer_avatar,
            "sentiment_category": r.sentiment_category,
            "sentiment_score": r.sentiment_score,
            "language": r.language,
        }

    data = [to_dict(r) for r in rows]
    from math import ceil

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "pages": ceil(total / limit) if limit else 1,
        "data": data,
    }


# ─────────────────────────────────────────────────────────────
# Optional: Minimal GBP connectivity (guarded)
# ─────────────────────────────────────────────────────────────
@router.get("/google/business")
def get_google_business_info(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    _validate_token(x_api_key, authorization)
    return _google_business_accounts()
