# FILE: app/routes/dashboard.py
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Company
# from ..auth import get_current_user  # Uncomment when authentication is ready
import os

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/", name="dashboard")
@router.get("/{company_id}", name="dashboard_with_company")
async def get_dashboard(
    request: Request,
    company_id: int | None = None,
    db: Session = Depends(get_db),
    # current_user = Depends(get_current_user)  # Add later for user-specific access
):
    """
    Render the main dashboard page.
    If company_id is provided in URL, pre-select that company.

    This route ALSO injects the Google Maps JS API key into the template so that
    the Places Autocomplete in the 'Add Company' modal can initialize.

    Expected environment variables (one of these must be set):
      - GOOGLE_MAPS_API_KEY        (used for Maps JavaScript + Places on frontend)
      - GOOGLE_PLACES_API_KEY      (backend server-to-server calls; not used in script tag)

    NOTE: We prefer GOOGLE_MAPS_API_KEY for the <script> tag because the Maps JS runtime
    runs in the browser and expects a Maps/Browser key configured with HTTP referrer
    restrictions for your domain(s).
    """
    initial_company = None
    if company_id:
        initial_company = db.query(Company).filter(Company.id == company_id).first()

    # Resolve the key for the front-end script tag.
    # We use GOOGLE_MAPS_API_KEY specifically for the browser (JS).
    google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")

    # Non-breaking diagnostics flags for the template (optional UI banner).
    diagnostics = {
        "maps_key_present": bool(google_maps_api_key),
        # You can add your production hostname checks here if needed
    }

    # If you want a HARD fail when key is missing, uncomment the next 2 lines.
    # if not google_maps_api_key:
    #     raise HTTPException(status_code=500, detail="Google Maps API key not configured")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "current_company_id": company_id or 0,
            "company_name": initial_company.name if initial_company else None,
            "google_maps_api_key": google_maps_api_key,  # ← used by <script src="...key={{ google_maps_api_key }}...">
            "diagnostics": diagnostics,                  # ← optional banner in template
        }
    )
