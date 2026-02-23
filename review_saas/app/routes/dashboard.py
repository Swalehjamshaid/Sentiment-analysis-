# FILE: app/routes/dashboard.py

from __future__ import annotations

import os
import io
import csv
import logging
from typing import Optional, Dict, Any, List, Tuple, Literal
from datetime import datetime, timedelta, timezone

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Path, Header, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..db import get_db
from ..models import Company, Review
from ..services.analysis import (
    dashboard_payload,            # unified payload for dashboard cards + charts
    reviews_table,                # server-side paginated table
    metrics_block, trend_block,   # optional granular chart endpoints
    sentiment_block, sources_block,
    heatmap_block, keywords_block,
    alerts_block, revenue_block,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# ─────────────────────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────────────────────
logger = logging.getLogger("dashboard")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────
GOOGLE_MAPS_API_KEY = os.getenv(
    "GOOGLE_MAPS_API_KEY",
    "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg",
)
GOOGLE_PLACES_API_KEY = os.getenv(
    "GOOGLE_PLACES_API_KEY",
    "AIzaSyCZ2a7vc0r9k3U7IFAMRQnYgmZwdx5RYjg",
)
API_TOKEN = os.getenv("API_TOKEN")
_G_TIMEOUT: Tuple[int, int] = (5, 15)  # connect, read


# ─────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────
def _validate_token(x_api_key: Optional[str], authorization: Optional[str]) -> None:
    """Optional API token guard."""
    if not API_TOKEN:
        return
    token = (x_api_key or "").strip()
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token != API_TOKEN:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API token")

def _parse_date(s: Optional[str]) -> Optional[datetime]:
    """Accept 'YYYY-MM-DD' or ISO string and return tz-aware UTC datetime."""
    if not s:
        return None
    try:
        # Try standard YYYY-MM-DD
        d = datetime.strptime(s, "%Y-%m-%d")
        return d.replace(tzinfo=timezone.utc)
    except Exception:
        try:
            # Try ISO format
            d = datetime.fromisoformat(s)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            return None

def _google_places_details(place_id: str, language: Optional[str] = None) -> Dict[str, Any]:
    """Fetch Place Details from Google."""
    api_key = GOOGLE_PLACES_API_KEY or GOOGLE_MAPS_API_KEY
    if not api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google Places API not configured")
    
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    fields = ",".join([
        "name", "formatted_address", "address_components", "geometry",
        "website", "international_phone_number", "rating",
        "user_ratings_total", "url",
    ])
    params = {"place_id": place_id, "fields": fields, "key": api_key}
    if language:
        params["language"] = language
    try:
        resp = requests.get(url, params=params, timeout=_G_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        g_status = payload.get("status")
        if g_status == "ZERO_RESULTS":
            return {}
        if g_status != "OK":
            logger.warning(f"Places Details status={g_status} err={payload.get('error_message')}")
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Google Places status: {g_status}")
        return payload.get("result", {}) or {}
    except requests.RequestException as e:
        logger.error(f"Places Details failed: {e}")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Google Places request failed")

def _extract_city(components: List[Dict[str, Any]]) -> Optional[str]:
    """Extract city from Google address components."""
    for comp in components or []:
        types = comp.get("types", [])
        if any(t in types for t in ["locality", "postal_town", "administrative_area_level_2"]):
            return comp.get("long_name")
    return None


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@router.get("/init")
def dashboard_init(db: Session = Depends(get_db)):
    """Inexpensive bootstrap data for dashboard sidebar and status."""
    companies = (
        db.query(Company)
          .with_entities(Company.id, Company.name, Company.city, Company.status)
          .filter(Company.status == "active")
          .order_by(Company.created_at.desc())
          .all()
    )
    return {
        "companies": [{"id": c.id, "name": c.name, "city": c.city, "status": c.status} for c in companies],
        "env": {
            "google_maps_key_present": bool(GOOGLE_MAPS_API_KEY),
            "google_places_key_present": bool(GOOGLE_PLACES_API_KEY),
        }
    }

@router.get("/companies")
def companies_list(
    q: Optional[str] = Query(None, description="search by name/city/address"),
    status: Optional[str] = Query("active"),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Company)
    if status:
        query = query.filter(Company.status == status)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(Company.name.ilike(term), Company.city.ilike(term), Company.address.ilike(term))
        )
    total = query.count()
    rows = query.order_by(Company.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    
    data = [{
        "id": c.id, "name": c.name, "city": c.city, "status": c.status,
        "created_at": c.created_at.replace(tzinfo=timezone.utc).isoformat() if c.created_at else None
    } for c in rows]
    
    from math import ceil
    return {"page": page, "limit": limit, "total": total, "pages": ceil(total / limit) if limit else 1, "data": data}

@router.post("/companies")
def companies_create(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    language: Optional[str] = Query(None),
):
    _validate_token(x_api_key, authorization)
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "name is required")

    place_id = payload.get("place_id")
    if place_id:
        exists = db.query(Company).filter(Company.place_id == place_id).first()
        if exists:
            raise HTTPException(status.HTTP_409_CONFLICT, "Place already registered")

    # Initial fallbacks
    city = payload.get("city")
    address = payload.get("address")
    phone = payload.get("phone")
    email = payload.get("email")
    website = payload.get("website")
    lat, lng = payload.get("lat"), payload.get("lng")

    if place_id:
        r = _google_places_details(place_id, language=language)
        name = r.get("name", name)
        address = r.get("formatted_address", address)
        phone = r.get("international_phone_number", phone)
        website = r.get("website", website)
        city = _extract_city(r.get("address_components") or []) or city
        loc = r.get("geometry", {}).get("location", {})
        lat = loc.get("lat", lat)
        lng = loc.get("lng", lng)

    row = Company(
        name=name,
        place_id=place_id,
        city=city,
        address=address,
        phone=phone,
        email=email,
        website=website,
        lat=lat, lng=lng,
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id, "name": row.name, "city": row.city, "status": row.status,
        "place_id": row.place_id, "lat": row.lat, "lng": row.lng
    }

@router.delete("/companies/{company_id}")
def companies_delete(
    company_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    _validate_token(x_api_key, authorization)
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    db.delete(c)
    db.commit()
    return {"ok": True, "deleted": company_id}

@router.get("/summary/{company_id}")
def dashboard_summary(
    company_id: int = Path(..., ge=1),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Unified call for all dashboard KPIs, charts, and AI insights."""
    return dashboard_payload(db, company_id, start, end)

@router.get("/table")
def dashboard_table(
    company_id: int = Query(..., ge=1),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=500),
    q: Optional[str] = Query(None, min_length=1, description="search reviews"),
    sort: str = Query("review_date"),
    order: Literal["asc", "desc"] = Query("desc"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Paginated table for the reviews grid."""
    return reviews_table(
        db=db, company_id=company_id, page=page, limit=limit,
        search=q, sort=sort, order=order, start=start, end=end,
    )

# ─────────────────────────────────────────────────────────────
# Granular Endpoints
# ─────────────────────────────────────────────────────────────

@router.get("/metrics")
def metrics(company_id: int = Query(..., ge=1), start: Optional[str] = None, end: Optional[str] = None, db: Session = Depends(get_db)):
    return metrics_block(db, company_id, start, end)

@router.get("/trend")
def trend(company_id: int = Query(..., ge=1), start: Optional[str] = None, end: Optional[str] = None, db: Session = Depends(get_db)):
    return trend_block(db, company_id, start, end)

@router.get("/sentiment")
def sentiment(company_id: int = Query(..., ge=1), start: Optional[str] = None, end: Optional[str] = None, db: Session = Depends(get_db)):
    return sentiment_block(db, company_id, start, end)

@router.get("/sources")
def sources(company_id: int = Query(..., ge=1), start: Optional[str] = None, end: Optional[str] = None, db: Session = Depends(get_db)):
    return sources_block(db, company_id, start, end)

@router.get("/heatmap")
def heatmap(company_id: int = Query(..., ge=1), start: Optional[str] = None, end: Optional[str] = None, db: Session = Depends(get_db)):
    return heatmap_block(db, company_id, start, end)

@router.get("/keywords")
def keywords(company_id: int = Query(..., ge=1), start: Optional[str] = None, end: Optional[str] = None, top_n: int = 20, db: Session = Depends(get_db)):
    return keywords_block(db, company_id, start, end, top_n=top_n)

@router.get("/alerts")
def alerts(company_id: int = Query(..., ge=1), start: Optional[str] = None, end: Optional[str] = None, window_days: int = 14, db: Session = Depends(get_db)):
    return alerts_block(db, company_id, start, end, window_days=window_days)

@router.get("/revenue")
def revenue(company_id: int = Query(..., ge=1), start: Optional[str] = None, end: Optional[str] = None, months_back: int = 6, db: Session = Depends(get_db)):
    return revenue_block(db, company_id, start, end, months_back=months_back)

# ─────────────────────────────────────────────────────────────
# CSV Export
# ─────────────────────────────────────────────────────────────
@router.get("/export")
def export_reviews_csv(
    company_id: int = Query(..., ge=1),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Review).filter(Review.company_id == company_id)
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)

    if start_dt:
        q = q.filter(Review.review_date >= start_dt)
    if end_dt:
        # If end_dt is just a date, include the full day
        if end_dt.hour == 0 and end_dt.minute == 0 and end_dt.second == 0:
            q = q.filter(Review.review_date < (end_dt + timedelta(days=1)))
        else:
            q = q.filter(Review.review_date <= end_dt)

    q = q.order_by(Review.review_date.desc())

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "review_date", "rating", "text", "reviewer_name",
        "sentiment_category", "sentiment_score", "keywords", "language"
    ])
    for r in q.all():
        writer.writerow([
            r.id,
            r.review_date.replace(tzinfo=timezone.utc).isoformat() if r.review_date else "",
            r.rating if r.rating is not None else "",
            (r.text or "").replace("\n", " ").strip(),
            r.reviewer_name or "",
            r.sentiment_category or "",
            r.sentiment_score if r.sentiment_score is not None else "",
            r.keywords or "",
            r.language or "",
        ])
    buf.seek(0)
    filename = f"reviews_company_{company_id}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
