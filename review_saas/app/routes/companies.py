# filename: app/routes/companies.py

from **future** import annotations

import json
import logging
import asyncio
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, Query, Request, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse
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
raise HTTPException(
status_code=status.HTTP_401_UNAUTHORIZED,
detail="Unauthorized"
)

# ─────────────────────────────────────────

# Lightweight Google Places REST client

# ─────────────────────────────────────────

class _GMapsClient:

```
BASE = "https://maps.googleapis.com/maps/api/place"

def __init__(
    self,
    api_key: str,
    language: Optional[str] = None,
    region: Optional[str] = None,
    timeout: int = 10,
):
    if not api_key:
        raise RuntimeError("Google API key is missing")

    self.api_key = api_key
    self.language = language
    self.region = region
    self.timeout = timeout

def _get_json(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:

    params["key"] = self.api_key

    if self.language:
        params["language"] = self.language

    if self.region:
        params["region"] = self.region

    url = f"{self.BASE}/{path}?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ReviewSaaS/1.0"}
    )

    try:
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as ex:
        raise RuntimeError(f"Network error contacting Google Places: {ex}")

    status_val = payload.get("status")

    if status_val not in ("OK", "ZERO_RESULTS"):
        msg = payload.get("error_message", status_val)
        raise RuntimeError(f"Google Places error: {msg}")

    return payload

def places_autocomplete(self, input_text: str) -> List[Dict[str, Any]]:

    data = self._get_json(
        "autocomplete/json",
        {
            "input": input_text,
            "types": "establishment",
        },
    )

    return data.get("predictions", [])

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

    data = self._get_json(
        "details/json",
        {
            "place_id": place_id,
            "fields": fields,
        },
    )

    return data
```

def _get_gmaps_client() -> Optional[_GMapsClient]:

```
key = settings.GOOGLE_API_KEY

if not key:
    logger.warning("Google API key not configured")
    return None

language = getattr(settings, "GOOGLE_PLACES_LANGUAGE", None)
region = getattr(settings, "GOOGLE_PLACES_REGION", None)

try:
    return _GMapsClient(
        api_key=key,
        language=language,
        region=region
    )
except Exception as ex:
    logger.warning("Failed to initialize Google Places client: %s", ex)
    return None
```

# ─────────────────────────────────────────

# Google Autocomplete Endpoint

# ─────────────────────────────────────────

@router.get("/google_autocomplete")
async def google_autocomplete(
request: Request,
input: str = Query(..., min_length=1, max_length=120),
):

```
_require_user(request)

client = _get_gmaps_client()

if not client:
    return JSONResponse(
        status_code=503,
        content={"error": "Google Places client not configured"},
    )

try:

    res = await asyncio.to_thread(
        client.places_autocomplete,
        input
    )

    predictions = [
        {
            "description": p.get("description"),
            "place_id": p.get("place_id"),
        }
        for p in res
    ]

    return {"predictions": predictions}

except Exception as ex:

    logger.exception("Google autocomplete failed: %s", ex)

    return JSONResponse(
        status_code=502,
        content={"error": f"Autocomplete service error: {str(ex)}"},
    )
```

# ─────────────────────────────────────────

# Google Place Details

# ─────────────────────────────────────────

@router.get("/google/place/details")
async def google_place_details(
request: Request,
place_id: str = Query(..., min_length=5),
):

```
_require_user(request)

client = _get_gmaps_client()

if not client:
    raise HTTPException(
        status_code=503,
        detail="Google Places client not configured",
    )

try:

    data = await asyncio.to_thread(
        client.place_details,
        place_id
    )

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

    raise HTTPException(
        status_code=502,
        detail=f"Google place lookup failed: {str(ex)}",
    )
```

# ─────────────────────────────────────────

# Companies List API

# ─────────────────────────────────────────

@router.get("/companies")
async def companies_list(
request: Request,
page: int = 1,
size: int = 20,
q: Optional[str] = None,
):

```
_require_user(request)

page = max(1, page)
size = max(1, min(100, size))

async with get_session() as session:

    stmt = select(Company)

    if q:
        stmt = stmt.where(Company.name.ilike(f"%{q}%"))

    stmt = stmt.order_by(desc(Company.created_at))

    rows = (
        await session.execute(
            stmt.offset((page - 1) * size).limit(size)
        )
    ).scalars().all()

    data = []

    for c in rows:

        stats = (
            await session.execute(
                select(
                    func.count(Review.id),
                    func.avg(Review.rating),
                ).where(Review.company_id == c.id)
            )
        ).first()

        data.append(
            {
                "id": int(c.id),
                "name": c.name,
                "place_id": getattr(c, "google_place_id", ""),
                "address": getattr(c, "address", ""),
                "review_count": int(stats[0] or 0),
                "avg_rating": round(float(stats[1] or 0), 2),
            }
        )

    return data
```

# ─────────────────────────────────────────

# Add Company

# ─────────────────────────────────────────

@router.post("/companies")
async def add_company(
request: Request,
background: BackgroundTasks,
company_in: CompanyCreate,
):

```
_require_user(request)

async with get_session() as session:

    existing = await session.execute(
        select(Company).where(
            Company.google_place_id == company_in.place_id
        )
    )

    existing_company = existing.scalar_one_or_none()

    if existing_company:
        return {
            "status": "exists",
            "company": {
                "id": int(existing_company.id),
                "name": existing_company.name,
                "place_id": existing_company.google_place_id,
                "address": existing_company.address,
            },
        }

    c = Company(
        name=company_in.name.strip(),
        google_place_id=company_in.place_id.strip(),
        address=company_in.address or "",
    )

    session.add(c)

    await session.commit()
    await session.refresh(c)

client = getattr(request.app.state, "reviews_client", None)

if run_batch_review_ingestion and client:
    background.add_task(
        run_batch_review_ingestion,
        client=client,
        companies=[c],
    )

return {
    "status": "ok",
    "company": {
        "id": int(c.id),
        "name": c.name,
        "place_id": c.google_place_id,
        "address": c.address,
    },
}
```

# ─────────────────────────────────────────

# Delete Company

# ─────────────────────────────────────────

@router.post("/companies/{company_id}/delete")
async def delete_company(request: Request, company_id: int):

```
_require_user(request)

async with get_session() as session:

    comp = await session.get(Company, company_id)

    if not comp:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    await session.delete(comp)
    await session.commit()

return RedirectResponse(
    url="/dashboard",
    status_code=302,
)
```
