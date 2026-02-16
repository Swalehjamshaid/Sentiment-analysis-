# review_saas/app/routes/companies.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
import bleach, os, re
from datetime import datetime

from ..db import get_db
from ..models import Company, User
from ..schemas import CompanyCreate
from ..services.google_places import validate_place_id
from ..deps import get_current_user

# Try to reuse a central templates instance if your app already defines one.
# If not present, fall back to a local Jinja2Templates pointing to ./templates
try:
    # If you expose a shared 'templates' somewhere (adjust import if needed)
    from ..urls import templates  # optional; remove if not present in your project
except Exception:
    templates = Jinja2Templates(directory="templates")

# Load API key from config/env so we can inject it into the companies UI page.
try:
    from ..config import GOOGLE_PLACES_API_KEY
except Exception:
    GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

router = APIRouter(prefix="/companies", tags=["companies"])


# -------------------- UI PAGE (injects Google API key) --------------------
@router.get("/ui")
async def companies_ui(request: Request, current_user: User = Depends(get_current_user)):
    """
    Renders the Companies UI page and injects GOOGLE_PLACES_API_KEY for the
    Google Maps JS SDK (libraries=places) used by the front-end autocomplete.
    """
    return templates.TemplateResponse(
        "companies.html",
        {
            "request": request,
            "GOOGLE_PLACES_API_KEY": GOOGLE_PLACES_API_KEY or "",
            "user": current_user,
        },
    )


# ----------------------------- Create Company -----------------------------
@router.post("/")
async def add_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not (payload.name or payload.place_id or payload.maps_url):
        raise HTTPException(status_code=400, detail="Provide at least one: name, place_id, or maps_url")

    # Try to pull place_id from maps_url if place_id wasn't provided.
    place_id = (payload.place_id or "").strip() or None
    if payload.maps_url and not place_id:
        # Support both q=place_id:XYZ and place_id=XYZ styles
        m = re.search(r"(?:[?&]q=place_id:|[?&]place_id=)([A-Za-z0-9_-]+)", payload.maps_url)
        if m:
            place_id = m.group(1)

    # Optional: validate place_id using your Google Places service
    if place_id:
        try:
            await validate_place_id(place_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Google Place ID")

    name = bleach.clean((payload.name or "").strip(), strip=True) or None
    city = bleach.clean((payload.city or "").strip(), strip=True) or None

    comp = Company(
        owner_user_id=current_user.id,
        name=name,
        place_id=place_id,
        maps_url=payload.maps_url,
        city=city
    )
    db.add(comp)
    try:
        db.commit(); db.refresh(comp)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Duplicate company for this user")
    return {"id": comp.id}


# ------------------------------ List Companies -----------------------------
@router.get("/")
async def list_companies(
    q: str | None = None,
    city: str | None = None,
    status: str | None = None,
    place_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Company).filter(Company.owner_user_id == current_user.id)
    if q:
        query = query.filter(Company.name.ilike(f"%{q}%"))
    if city:
        query = query.filter(Company.city.ilike(f"%{city}%"))
    if status:
        query = query.filter(Company.status == status)
    if place_id:
        query = query.filter(Company.place_id == place_id)
    return [{
        "id": c.id, "name": c.name, "place_id": c.place_id, "maps_url": c.maps_url,
        "city": c.city, "status": c.status, "logo_url": c.logo_url,
        "created_at": c.created_at.isoformat()
    } for c in query.all()]


# ------------------------------ Edit Company -------------------------------
@router.put("/{company_id}")
async def edit_company(
    company_id: int,
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    c = db.query(Company).get(company_id)
    if not c: raise HTTPException(status_code=404, detail="Not found")
    if c.owner_user_id != current_user.id: raise HTTPException(status_code=403, detail="Forbidden")

    if payload.name is not None:
        c.name = bleach.clean(payload.name, strip=True)
    if payload.city is not None:
        c.city = bleach.clean(payload.city, strip=True)
    if payload.maps_url is not None:
        c.maps_url = payload.maps_url
        # If maps_url changed, try to refresh place_id too
        m = re.search(r"(?:[?&]q=place_id:|[?&]place_id=)([A-Za-z0-9_-]+)", c.maps_url or "")
        if m:
            c.place_id = m.group(1)

    db.commit()
    return {"message": "Updated"}


# ----------------------------- Delete Company ------------------------------
@router.delete("/{company_id}")
async def delete_company(
    company_id: int,
    confirm: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not confirm:
        raise HTTPException(status_code=400, detail="Please confirm deletion")
    c = db.query(Company).get(company_id)
    if not c: raise HTTPException(status_code=404, detail="Not found")
    if c.owner_user_id != current_user.id: raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(c); db.commit()
    return {"message": "Deleted"}


# ---------------------- Logo Upload (≤2MB, JPEG/PNG) -----------------------
@router.post("/{company_id}/logo")
async def upload_logo(
    company_id: int,
    logo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    c = db.query(Company).get(company_id)
    if not c: raise HTTPException(status_code=404, detail="Not found")
    if c.owner_user_id != current_user.id: raise HTTPException(status_code=403, detail="Forbidden")

    if logo.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=400, detail="Only JPEG/PNG allowed")
    content = await logo.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Max 2MB allowed")

    os.makedirs("uploads/company_logos", exist_ok=True)
    safe_base = os.path.basename(logo.filename or "logo.png").replace("..", "")
    safe_name = f"{int(datetime.utcnow().timestamp())}_{safe_base}"
    path = os.path.join("uploads", "company_logos", safe_name)
    with open(path, "wb") as f:
        f.write(content)

    c.logo_url = f"/uploads/company_logos/{safe_name}"
    db.commit()
    return {"logo_url": c.logo_url}
