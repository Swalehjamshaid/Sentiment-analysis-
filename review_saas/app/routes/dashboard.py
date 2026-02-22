# FILE: app/routes/dashboard.py
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
from ..db import get_db
from ..models import Company
# from ..auth import get_current_user  # Uncomment when auth is implemented
import os

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


def _get_google_maps_js_key() -> Optional[str]:
    """
    Prefer GOOGLE_MAPS_API_KEY for browser JavaScript (Maps JS API + Places Autocomplete).
    Fall back to GOOGLE_PLACES_API_KEY only if the former is missing.
    """
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if key:
        return key
    fallback = os.getenv("GOOGLE_PLACES_API_KEY")
    if fallback:
        print("Warning: Using GOOGLE_PLACES_API_KEY for browser – prefer GOOGLE_MAPS_API_KEY for JS API")
        return fallback
    return None


@router.get("/", name="dashboard")
@router.get("/{company_id}", name="dashboard_with_company")
async def get_dashboard(
    request: Request,
    company_id: Optional[int] = None,
    db: Session = Depends(get_db),
    # current_user = Depends(get_current_user)  # ← enable later for ownership filtering
):
    """
    Renders the main Review Intelligence dashboard.
    
    - If company_id is in the URL path (e.g. /dashboard/3), pre-selects that company.
    - Injects Google Maps JavaScript API key for client-side Places Autocomplete.
    - Includes basic diagnostics (useful during dev / onboarding).
    """
    initial_company = None
    if company_id:
        initial_company = (
            db.query(Company)
            .filter(Company.id == company_id)
            # .filter(Company.owner_id == current_user.id)  # ← add when auth ready
            .first()
        )
        if not initial_company:
            raise HTTPException(status_code=404, detail="Company not found")

    maps_js_key = _get_google_maps_js_key()

    # Optional: raise hard error in production if key missing
    # if not maps_js_key:
    #     raise HTTPException(500, "Google Maps JavaScript API key not configured")

    diagnostics = {
        "maps_js_key_present": bool(maps_js_key),
        "maps_key_source": "GOOGLE_MAPS_API_KEY" if os.getenv("GOOGLE_MAPS_API_KEY") else
                           "GOOGLE_PLACES_API_KEY (fallback)" if os.getenv("GOOGLE_PLACES_API_KEY") else
                           "MISSING",
        "environment": os.getenv("ENVIRONMENT", "development"),
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "current_company_id": company_id or 0,
            "initial_company_name": initial_company.name if initial_company else None,
            "google_maps_api_key": maps_js_key,
            "diagnostics": diagnostics,
            # Add more context if needed, e.g.:
            # "user": current_user,
        }
    )
