# filename: app/routes/companies.py
from __future__ import annotations

import json
import logging
import asyncio
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, Query, Request, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from sqlalchemy import desc, func, select

from app.core.db import get_session
from app.core.models import Company, Review
from app.core.config import settings

# Optional Review ingestion
try:
    from app.services.google_reviews import run_batch_review_ingestion
except Exception:
    run_batch_review_ingestion = None

router = APIRouter(tags=["companies"], prefix="/api")
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.companies")

# ─────────────────────────────────────────
# JSON Schema for Adding Company
# ─────────────────────────────────────────
class CompanyCreate(BaseModel):
    name: str
    place_id: str
    address: Optional[str] = None

# ─────────────────────────────────────────
# Auth helper
# ─────────────────────────────────────────
def _require_user(request: Request) -> None:
    if not request.session.get("user"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

# ─────────────────────────────────────────
# Lightweight Google Places REST client
# (avoids third-party googlemaps dependency)
# ─────────────────────────────────────────
class _GMapsClient:
    BASE = "https://maps.googleapis.com/maps/api/place"

    def __init__(self, api_key: str, language: Optional[str] = None, region: Optional[str] = None, timeout: int = 10):
        if not api_key:
            raise RuntimeError("Google API key is missing")
        self.api_key = api_key
        self.language = language
        self.region = region
        self.timeout = timeout

    def _get_json(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        # Add required params
        params["key"] = self.api_key
        if self.language:
            params["language"] = self.language
        if self.region:
            params["region"] = self.region

        url = f"{self.BASE}/{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "ReviewSaaS/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as ex:
            raise RuntimeError(f"Network error contacting Google Places: {ex}")

        status_val = payload.get("status")
        # Google Places returns OK / ZERO_RESULTS as non-error; others are errors
        if status_val not in ("OK", "ZERO_RESULTS"):
            msg = payload.get("error_message", status_val)
            raise RuntimeError(f"Google Places error: {msg}")
        return payload

    # Mirrors googlemaps.Client.places_autocomplete signature semantically
    def places_autocomplete(self, input_text: str) -> List[Dict[str, Any]]:
        data = self._get_json("autocomplete/json", {
            "input": input_text,
            "types": "establishment",
        })
        return data.get("predictions", [])

    # Simple place details
    def place_details(self, place_id: str) -> Dict[str, Any]:
        fields = ",".join([
            "place_id",
            "name",
            "formatted_address",
            "geometry/location",
            "website",
            "url",
            "rating",
            "user_ratings_total",
        ])
        data = self._get_json("details/json", {
            "place_id": place_id,
            "fields": fields,
        })
        return data  # includes top-level status, result, etc.

def _resolve_google_api_key() -> str:
    # Support both names to avoid configuration mismatch
    return (
        getattr(settings, "GOOGLE_PLACES_API_KEY", None)
        or getattr(settings, "GOOGLE_MAPS_API_KEY", None)
        or ""
    )

def _gmaps_prefs() -> Tuple[Optional[str], Optional[str]]:
    language = getattr(settings, "GOOGLE_PLACES_LANGUAGE", None)
    region = getattr(settings, "GOOGLE_PLACES_REGION", None)
    return language, region

def _get_gmaps_client() -> Optional[_GMapsClient]:
    key = _resolve_google_api_key()
    if not key:
        logger.warning("Google API key not configured (GOOGLE_PLACES_API_KEY/GOOGLE_MAPS_API_KEY)")
        return None
    language, region = _gmaps_prefs()
    try:
        return _GMapsClient(api_key=key, language=language, region=region)
    except Exception as ex:
        logger.warning("Failed to initialize Google Places client: %s", ex)
        return None

# ─────────────────────────────────────────
# Google Autocomplete Endpoint
# ─────────────────────────────────────────
@router.get("/google_autocomplete")
async def google_autocomplete(request: Request, input: str = Query(..., min_length=1, max_length=120)):
    _require_user(request)
    client = _get_gmaps_client()
    if not client:
        return JSONResponse(
            status_code=503,
            content={"error": "Google Places client not configured"}
        )

    try:
        # `places_autocomplete` is sync; run in thread
        res = await asyncio.to_thread(client.places_autocomplete, input)
        predictions = [{"description": p.get("description"), "place_id": p.get("place_id")} for p in res]
        return {"predictions": predictions}
    except Exception as ex:
        logger.exception("Google autocomplete failed: %s", ex)
        return JSONResponse(
            status_code=502,
            content={"error": f"Autocomplete service error: {str(ex)}"}
        )

# ─────────────────────────────────────────
# Google Place Details
# ─────────────────────────────────────────
@router.get("/google/place/details")
async def google_place_details(request: Request, place_id: str = Query(..., min_length=5)):
    _require_user(request)

    # Prefer local REST client; fall back to optional service if present
    client = _get_gmaps_client()
    svc_place_details = None
    try:
        from app.services.google_places import place_details as _svc_place_details  # optional
        svc_place_details = _svc_place_details
    except Exception:
        svc_place_details = None

    try:
        if client:
            data = await asyncio.to_thread(client.place_details, place_id)
        elif svc_place_details:
            # If a custom service exists (legacy), use it
            data = await asyncio.to_thread(svc_place_details, place_id)
        else:
            raise RuntimeError("Google Places client/service not configured")

        result = data.get("result", {})
        return {
            "name": result.get("name"),
            "place_id": result.get("place_id"),
            "address": result.get("formatted_address"),
            "rating": result.get("rating"),
            "user_ratings_total": result.get("user_ratings_total"),
            "website": result.get("website"),
            "url": result.get("url"),
            "location": (result.get("geometry") or {}).get("location", {}),
        }
    except Exception as ex:
        logger.exception("Google place details failed: %s", ex)
        raise HTTPException(status_code=502, detail=f"Google place lookup failed: {str(ex)}")

# ─────────────────────────────────────────
# Companies Data Helper
# ─────────────────────────────────────────
async def _get_companies_data(page: int = 1, size: int = 20, q: Optional[str] = None) -> Dict[str, Any]:
    page = max(1, page)
    size = max(1, min(100, size))
    async with get_session() as session:
        stmt = select(Company)
        if q:
            stmt = stmt.where(Company.name.ilike(f"%{q}%"))
        stmt = stmt.order_by(desc(Company.created_at))

        total_stmt = select(func.count(Company.id))
        if q:
            total_stmt = total_stmt.where(Company.name.ilike(f"%{q}%"))

        total = (await session.execute(total_stmt)).scalar() or 0
        rows = (await session.execute(stmt.offset((page - 1) * size).limit(size))).scalars().all()

        data: List[Dict[str, Any]] = []
        for c in rows:
            stats = (await session.execute(
                select(func.count(Review.id), func.avg(Review.rating))
                .where(Review.company_id == c.id)
            )).first()

            data.append({
                "id": int(c.id),
                "name": c.name,
                "place_id": getattr(c, "place_id", ""),
                "address": getattr(c, "address", ""),
                "review_count": int(stats[0] or 0),
                "avg_rating": round(float(stats[1] or 0), 2)
            })

    return {"page": page, "size": size, "total": int(total), "items": data}

# ─────────────────────────────────────────
# Companies List API
# ─────────────────────────────────────────
@router.get("/companies")
async def companies_list(request: Request, page: int = 1, size: int = 20, q: Optional[str] = None):
    _require_user(request)
    data = await _get_companies_data(page, size, q)
    # Return only the items array for front-end mapping
    return data["items"]

# ─────────────────────────────────────────
# Add Company
# ─────────────────────────────────────────
@router.post("/companies")
async def add_company(
    request: Request,
    background: BackgroundTasks,
    company_in: CompanyCreate,
):
    _require_user(request)
    async with get_session() as session:
        c = Company(
            name=company_in.name.strip(),
            place_id=company_in.place_id or "",
            address=company_in.address or ""
        )
        session.add(c)
        await session.commit()
        await session.refresh(c)

    # Trigger review ingestion if client is available
    client = getattr(request.app.state, "google_reviews_client", None)
    if run_batch_review_ingestion and client:
        # Pass ORM instance as before to keep existing signature unchanged
        background.add_task(run_batch_review_ingestion, client, [c])

    return {
        "status": "ok",
        "company": {"id": int(c.id), "name": c.name, "place_id": c.place_id, "address": c.address}
    }

# ─────────────────────────────────────────
# Delete Company
# ─────────────────────────────────────────
@router.post("/companies/{company_id}/delete")
async def delete_company(request: Request, company_id: int):
    _require_user(request)
    async with get_session() as session:
        comp = await session.get(Company, company_id)
        if not comp:
            raise HTTPException(status_code=404, detail="Company not found")
        await session.delete(comp)
        await session.commit()
    return RedirectResponse(url="/dashboard", status_code=302)
