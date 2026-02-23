# FILE: app/routes/dashboard.py

from __future__ import annotations

import os
import io
import csv
import logging
from typing import Optional, Dict, Any, List, Tuple, Literal
from datetime import datetime, timedelta, timezone

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Path, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

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
# Config (match the pattern you use in other routes)
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
    """Optional API token guard (only enforced if API_TOKEN is set)."""
    if not API_TOKEN:
        return
    token = (x_api_key or "").strip()
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token != API_TOKEN:
        raise HTTPException(401, "Invalid API token")

def _parse_date(s: Optional[str]) -> Optional[datetime]:
    """Accept 'YYYY-MM-DD' or ISO string and return tz-aware UTC datetime."""
    if not s:
        return None
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
        return d.replace(tzinfo=timezone.utc)
    except Exception:
        try:
            d = datetime.fromisoformat(s)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            return None

def _google_places_details(place_id: str, language: Optional[str] = None) -> Dict[str, Any]:
    """Small helper for Google Place Details (same approach as other routes)."""
    api_key = GOOGLE_PLACES_API_KEY or GOOGLE_MAPS_API_KEY
    if not api_key:
        raise HTTPException(503, "Google Places API not configured")
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
        status = payload.get("status")
        if status == "ZERO_RESULTS":
            return {}
        if status != "OK":
            logger.warning(f"Places Details status={status} err={payload.get('error_message')}")
            raise HTTPException(502, f"Google Places status: {status}")
        return payload.get("result", {}) or {}
    except requests.RequestException as e:
        logger.error(f"Places Details failed: {e}")
        raise HTTPException(502, "Google Places request failed")

def _extract_city(components: List[Dict[str, Any]]) -> Optional[str]:
    for comp in components or []:
        types = comp.get("types", [])
        if "locality" in types or "postal_town" in types or "administrative_area_level_2" in types:
            return comp.get("long_name")
    return None


# ─────────────────────────────────────────────────────────────
# 1) Dashboard bootstrap / initial data
# ─────────────────────────────────────────────────────────────
@router.get("/init")
def dashboard_init(db: Session = Depends(get_db)):
    """
    Returns inexpensive data to bootstrap the dashboard:
    - active companies (id, name, city, status)
    - environment flags (keys present)
    """
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


# ─────────────────────────────────────────────────────────────
# 2) Companies (for dashboard management)
#    NOTE: The front-end can still use /api/companies/* directly.
#    These endpoints are provided for convenience under /api/dashboard/*.
# ─────────────────────────────────────────────────────────────
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
    rows = (
        query.order_by(Company.created_at.desc())
             .offset((page - 1) * limit)
             .limit(limit)
             .all()
    )
    data = [{
        "id": c.id, "name": c.name, "city": c.city, "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None
    } for c in rows]
    from math import ceil
    return {"page": page, "limit": limit, "total": total, "pages": ceil(total / limit), "data": data}


@router.post("/companies")
def companies_create(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    language: Optional[str] = Query(None),
):
    """
    Minimal company creation for dashboard.
    Fields accepted: name, city, address, phone, email, website, place_id.
    If place_id is provided, we enrich from Google Places.
    """
    _validate_token(x_api_key, authorization)

    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(422, "name is required")

    # avoid duplicates by place_id if provided
    place_id = (payload.get("place_id") or None)
    if place_id:
        exists = db.query(Company).filter(Company.place_id == place_id).first()
        if exists:
            raise HTTPException(409, "Place already registered")

    city = payload.get("city")
    address = payload.get("address")
    phone = payload.get("phone")
    email = payload.get("email")
    website = payload.get("website")
    lat = payload.get("lat")
    lng = payload.get("lng")

    # Enrich via Places (optional)
    if place_id:
        r = _google_places_details(place_id, language=language)
        name = r.get("name", name)
        address = r.get("formatted_address", address)
        phone = r.get("international_phone_number", phone)
        website = r.get("website", website)
        city = _extract_city(r.get("address_components") or []) or city
        loc = (r.get("geometry") or {}).get("location") or {}
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
    """
    Delete a company and cascade its reviews (per your model constraints).
    """
    _validate_token(x_api_key, authorization)
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(404, "Company not found")
    db.delete(c)
    db.commit()
    return {"ok": True, "deleted": company_id}


# ─────────────────────────────────────────────────────────────
# 3) Unified Dashboard Summary (cards, charts, recommendations)
# ─────────────────────────────────────────────────────────────
@router.get("/summary/{company_id}")
def dashboard_summary(
    company_id: int = Path(..., ge=1),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    One call for dashboard.html to hydrate:
    - KPIs (total, avg_rating, risk)
    - Sentiments, daily series, trend, aspects, AI recs
    - Sources, heatmap, keywords, alerts, revenue proxy
    """
    return dashboard_payload(db, company_id, start, end)


# ─────────────────────────────────────────────────────────────
# 4) Table (server-side pagination) – used by reviews grid
# ─────────────────────────────────────────────────────────────
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
    return reviews_table(
        db=db,
        company_id=company_id,
        page=page,
        limit=limit,
        search=q,
        sort=sort,
        order=order,
        start=start,
        end=end,
    )


# ─────────────────────────────────────────────────────────────
# 5) Optional granular chart endpoints (if front-end prefers)
#    These all reuse the ai_insights math via services.analysis
# ─────────────────────────────────────────────────────────────
@router.get("/metrics")
def metrics(
    company_id: int = Query(..., ge=1),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return metrics_block(db, company_id, start, end)

@router.get("/trend")
def trend(
    company_id: int = Query(..., ge=1),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return trend_block(db, company_id, start, end)

@router.get("/sentiment")
def sentiment(
    company_id: int = Query(..., ge=1),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return sentiment_block(db, company_id, start, end)

@router.get("/sources")
def sources(
    company_id: int = Query(..., ge=1),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return sources_block(db, company_id, start, end)

@router.get("/heatmap")
def heatmap(
    company_id: int = Query(..., ge=1),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return heatmap_block(db, company_id, start, end)

@router.get("/keywords")
def keywords(
    company_id: int = Query(..., ge=1),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    top_n: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return keywords_block(db, company_id, start, end, top_n=top_n)

@router.get("/alerts")
def alerts(
    company_id: int = Query(..., ge=1),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    window_days: int = Query(14, ge=7, le=90),
    db: Session = Depends(get_db),
):
    return alerts_block(db, company_id, start, end, window_days=window_days)

@router.get("/revenue")
def revenue(
    company_id: int = Query(..., ge=1),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    months_back: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
):
    return revenue_block(db, company_id, start, end, months_back=months_back)


# ─────────────────────────────────────────────────────────────
# 6) CSV Export (filtered by date window)
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
        # include full end day if only date
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
            r.review_date.isoformat() if r.review_date else "",
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
