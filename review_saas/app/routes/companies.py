# FILE: app/routes/companies.py
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Path
from sqlalchemy.orm import Session, defer
from sqlalchemy import func
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
API_TOKEN = os.getenv("API_TOKEN")  # Optional server-side auth for POST

logger = logging.getLogger("companies")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

_G_TIMEOUT: Tuple[int, int] = (5, 10)  # connect / read timeout in seconds


def _extract_city_from_components(components: List[Dict[str, Any]]) -> Optional[str]:
    """
    Returns best-effort city from Google address components.
    Prefers 'locality'; falls back to 'postal_town' or admin level 2.
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
        status = payload.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            raise HTTPException(502, f"Google Places status: {status}")
        return payload.get("result", {}) or {}
    except requests.RequestException as e:
        logger.warning(f"Places Details failed for {place_id}: {e}")
        raise HTTPException(502, f"Google Places error: {str(e)}")


# ─────────────────────────────────────────────────────────────
# Helpers for dashboard serialization & filtering
# ─────────────────────────────────────────────────────────────
def _company_to_dict(c: Company) -> Dict[str, Any]:
    """Serialize a Company ORM instance to a plain dict for tables/JSON."""
    out = {
        "id": getattr(c, "id", None),
        "name": getattr(c, "name", None),
        "city": getattr(c, "city", None),
        "address": getattr(c, "address", None) if hasattr(c, "address") else None,
        "phone": getattr(c, "phone", None) if hasattr(c, "phone") else None,
        "email": getattr(c, "email", None) if hasattr(c, "email") else None,
        "website": getattr(c, "website", None) if hasattr(c, "website") else None,
        "status": getattr(c, "status", None),
        "place_id": getattr(c, "place_id", None),
        "created_at": getattr(c, "created_at", None),
        "lat": getattr(c, "lat", None) if hasattr(c, "lat") else None,
        "lng": getattr(c, "lng", None) if hasattr(c, "lng") else None,
        "description": getattr(c, "description", None) if hasattr(c, "description") else None,
    }
    # ISO format datetime for JSON safety
    if isinstance(out["created_at"], datetime):
        out["created_at"] = out["created_at"].isoformat()
    return out


def _apply_common_filters(query, search: Optional[str], status: Optional[str]):

    if status:
        query = query.filter(Company.status == status)

    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            (Company.name.ilike(s)) |
            (Company.city.ilike(s)) |
            (Company.address.ilike(s))
        )
    return query


# ─────────────────────────────────────────────────────────────
# 1. GET /api/companies - List companies (paginated, searchable)
# ─────────────────────────────────────────────────────────────
@router.get("/", response_model=List[CompanyResponse])
def get_companies(
    search: Optional[str] = Query(None, min_length=1, description="Search name, city or address"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(30, ge=5, le=200, description="Items per page"),
    status: Optional[str] = Query("active", description="Filter by status"),
    sort: str = Query("name", regex=r"^(name|city|created_at)$", description="Sort field"),
    order: str = Query("asc", regex=r"^(asc|desc)$", description="Sort direction"),
    db: Session = Depends(get_db),
):
    query = db.query(Company)

    # Optional: defer columns that may not exist yet in DB
    for col in ["lat", "lng", "email", "phone", "address", "description"]:
        if hasattr(Company, col):
            query = query.options(defer(getattr(Company, col)))

    # Filters
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

    if payload.name and payload.city:
        dup = db.query(Company).filter(
            Company.name.ilike(payload.name),
            Company.city.ilike(payload.city)
        ).first()
        if dup:
            raise HTTPException(409, "Company with same name & city already exists")

    # Start with input values
    name = payload.name
    city = payload.city
    address = payload.address
    phone = payload.phone
    website = getattr(payload, "website", None)
    lat = payload.lat
    lng = payload.lng

    # Enrich from Google
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
# 3. GET /api/companies/autocomplete - Google Places autocomplete
# ─────────────────────────────────────────────────────────────
@router.get("/autocomplete", response_model=List[Dict[str, str]])
def autocomplete_company(
    q: str = Query(..., min_length=2, description="Search term"),
    lat: Optional[float] = Query(None, description="Latitude for location bias"),
    lng: Optional[float] = Query(None, description="Longitude for location bias"),
    radius: Optional[int] = Query(50000, ge=1000, le=100000, description="Radius in meters"),
    language: Optional[str] = Query(None, description="Language code"),
):
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, "Google Places API not configured")

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
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/autocomplete/json",
            params=params,
            timeout=_G_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "OK":
            raise ValueError(f"Google status: {data.get('status')}")
        return [
            {"description": p.get("description"), "place_id": p.get("place_id")}
            for p in data.get("predictions", [])
        ]
    except Exception as e:
        logger.warning(f"Autocomplete failed: {e}")
        raise HTTPException(502, f"Google Autocomplete error: {str(e)}")


# ─────────────────────────────────────────────────────────────
# 4. GET /api/companies/details/{place_id} - Get full place details
# ─────────────────────────────────────────────────────────────
@router.get("/details/{place_id}", response_model=Dict[str, Any])
def google_details(
    place_id: str,
    language: Optional[str] = Query(None, description="Google response language"),
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
        "user_ratings_total": result.get("user_ratings_total"),
        "url": result.get("url"),
    }


# ─────────────────────────────────────────────────────────────
# 5. NEW: Dashboard Summary KPIs
#    GET /api/companies/summary
# ─────────────────────────────────────────────────────────────
@router.get("/summary", response_model=Dict[str, Any])
def companies_summary(
    status: Optional[str] = Query(None, description="Optional status filter for totals"),
    db: Session = Depends(get_db),
):
    base_q = db.query(Company)
    if status:
        base_q = base_q.filter(Company.status == status)

    total = db.query(func.count(Company.id)).scalar() or 0
    active = db.query(func.count(Company.id)).filter(Company.status == "active").scalar() or 0
    inactive = db.query(func.count(Company.id)).filter(Company.status == "inactive").scalar() or 0

    # Distinct cities
    cities_count = db.query(func.count(func.distinct(Company.city))).scalar() or 0

    # Last created_at
    last_created = db.query(func.max(Company.created_at)).scalar()
    last_created_iso = last_created.isoformat() if isinstance(last_created, datetime) else None

    return {
        "total": int(total),
        "active": int(active),
        "inactive": int(inactive),
        "cities": int(cities_count),
        "last_created_at": last_created_iso,
    }


# ─────────────────────────────────────────────────────────────
# 6. NEW: Dashboard Stats (charts)
#    GET /api/companies/stats
# ─────────────────────────────────────────────────────────────
@router.get("/stats", response_model=Dict[str, Any])
def companies_stats(
    top_cities: int = Query(10, ge=1, le=100, description="Top N cities by count"),
    months: int = Query(12, ge=1, le=36, description="How many months back for by_month series"),
    status: Optional[str] = Query(None, description="Optional status filter"),
    db: Session = Depends(get_db),
):
    # Counts by city
    city_q = db.query(Company.city, func.count(Company.id)).group_by(Company.city)
    if status:
        city_q = city_q.filter(Company.status == status)
    by_city_rows = city_q.order_by(func.count(Company.id).desc()).limit(top_cities).all()
    by_city = [{"city": c or "(Unknown)", "count": int(cnt)} for c, cnt in by_city_rows]

    # Time series by month (Python-side to be DB-agnostic)
    now = datetime.now(timezone.utc)
    start_month = (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
    months_list = []
    for i in range(months - 1, -1, -1):
        m = (start_month - timedelta(days=31 * i)).replace(day=1)
        months_list.append(m)

    # Pull created_at timestamps in the window
    earliest = months_list[0]
    ts_q = db.query(Company.created_at)
    if status:
        ts_q = ts_q.filter(Company.status == status)
    ts_q = ts_q.filter(Company.created_at >= earliest)
    created_list = [r[0] for r in ts_q.all() if isinstance(r[0], datetime)]

    # Count per month bucket
    counts_by_month: Dict[str, int] = {}
    for m in months_list:
        key = m.strftime("%Y-%m")
        counts_by_month[key] = 0

    for dtv in created_list:
        # normalize to month key
        key = dtv.strftime("%Y-%m")
        if key in counts_by_month:
            counts_by_month[key] += 1

    by_month = [{"month": k, "count": counts_by_month[k]} for k in sorted(counts_by_month.keys())]

    # Geo bounds
    lat_min = lat_max = lng_min = lng_max = None
    if hasattr(Company, "lat") and hasattr(Company, "lng"):
        gb_q = db.query(
            func.min(Company.lat), func.max(Company.lat),
            func.min(Company.lng), func.max(Company.lng),
        )
        if status:
            gb_q = gb_q.filter(Company.status == status)
        lat_min, lat_max, lng_min, lng_max = gb_q.first() or (None, None, None, None)

    return {
        "by_city": by_city,
        "by_month": by_month,
        "geo_bounds": {
            "lat_min": lat_min,
            "lat_max": lat_max,
            "lng_min": lng_min,
            "lng_max": lng_max,
        }
    }


# ─────────────────────────────────────────────────────────────
# 7. NEW: DataTables server-side endpoint
#    GET /api/companies/datatable
#    Supports: draw, start, length, search[value], order[0][column], order[0][dir]
# ─────────────────────────────────────────────────────────────
@router.get("/datatable", response_model=Dict[str, Any])
def companies_datatable(
    draw: int = Query(1, ge=0),
    start: int = Query(0, ge=0),
    length: int = Query(25, ge=1, le=500),
    # DataTables nested params via alias
    search_value: Optional[str] = Query(None, alias="search[value]"),
    order_col_idx: Optional[int] = Query(None, alias="order[0][column]"),
    order_dir: Optional[str] = Query("asc", alias="order[0][dir]", regex=r"^(asc|desc)$"),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    # Define exposed columns (index mapping for order)
    columns: List[str] = ["name", "city", "address", "created_at", "status"]
    order_by_col = "name"
    if order_col_idx is not None and 0 <= order_col_idx < len(columns):
        order_by_col = columns[order_col_idx]

    # Base queries
    base_q = db.query(Company)
    total = db.query(func.count(Company.id)).scalar() or 0

    # Filtered query
    filtered_q = _apply_common_filters(base_q, search_value, status)

    # Count filtered
    records_filtered = filtered_q.with_entities(func.count(Company.id)).scalar() or 0

    # Ordering
    order_attr = getattr(Company, order_by_col)
    if order_dir == "desc":
        filtered_q = filtered_q.order_by(order_attr.desc())
    else:
        filtered_q = filtered_q.order_by(order_attr.asc())

    # Paging
    data_rows = filtered_q.offset(start).limit(length).all()
    data = [_company_to_dict(c) for c in data_rows]

    return {
        "draw": draw,
        "recordsTotal": int(total),
        "recordsFiltered": int(records_filtered),
        "data": data,
    }


# ─────────────────────────────────────────────────────────────
# 8. NEW: Map markers for dashboard maps
#    GET /api/companies/markers
# ─────────────────────────────────────────────────────────────
@router.get("/markers", response_model=List[Dict[str, Any]])
def companies_markers(
    status: Optional[str] = Query(None, description="Status filter"),
    # Optional bounding box filter (WGS84)
    min_lat: Optional[float] = Query(None, description="Min latitude"),
    min_lng: Optional[float] = Query(None, description="Min longitude"),
    max_lat: Optional[float] = Query(None, description="Max latitude"),
    max_lng: Optional[float] = Query(None, description="Max longitude"),
    limit: int = Query(1000, ge=1, le=10000, description="Max markers returned"),
    db: Session = Depends(get_db),
):
    q = db.query(Company)
    if status:
        q = q.filter(Company.status == status)

    # Only include rows with coordinates if available
    if hasattr(Company, "lat") and hasattr(Company, "lng"):
        q = q.filter(Company.lat.isnot(None), Company.lng.isnot(None))
        # Apply bbox if complete
        if None not in (min_lat, min_lng, max_lat, max_lng):
            q = q.filter(
                Company.lat >= min_lat,
                Company.lat <= max_lat,
                Company.lng >= min_lng,
                Company.lng <= max_lng,
            )

    q = q.order_by(Company.created_at.desc()).limit(limit)
    rows = q.all()

    markers = []
    for c in rows:
        markers.append({
            "id": getattr(c, "id", None),
            "name": getattr(c, "name", None),
            "city": getattr(c, "city", None),
            "status": getattr(c, "status", None),
            "lat": getattr(c, "lat", None) if hasattr(c, "lat") else None,
            "lng": getattr(c, "lng", None) if hasattr(c, "lng") else None,
        })
    return markers


# ─────────────────────────────────────────────────────────────
# 9. NEW: Get a single company by ID (for detail modals)
#    GET /api/companies/{company_id}
#    NOTE: Keep this at the end to avoid conflicting with /details/{place_id}.
# ─────────────────────────────────────────────────────────────
@router.get("/{company_id}", response_model=CompanyResponse)
def get_company_by_id(
    company_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(404, "Company not found")
    return c
