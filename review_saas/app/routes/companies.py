# filename: review_saas/app/routes/companies.py
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company
from app.services.rbac import get_current_user

router = APIRouter()

@router.post("/companies/create")
async def create_company(
    request: Request,
    # CSRF input injected by {{ csrf_token() }} in the template
    csrf_token: str = Form(...),

    # Core
    name: str = Form(...),
    place_id: str = Form(""),

    # Address
    address: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    postal_code: str = Form(""),
    country: str = Form(""),

    # Location
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),

    # Contacts / links
    phone: str = Form(""),
    website: str = Form(""),
    google_url: str = Form(""),

    # Metrics
    rating: float | None = Form(None),
    user_ratings_total: int | None = Form(None),

    # CSV string of Google types
    types: str = Form(""),

    db: Session = Depends(get_db),
):
    # Auth
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    # CSRF validate (token stored in session by helper)
    session_token = request.session.get("_csrf")
    if not session_token or session_token != csrf_token:
        return RedirectResponse("/?error=csrf", status_code=302)

    # Create
    comp = Company(
        name=name.strip(),
        place_id=place_id.strip() or None,
        address=address,
        city=city,
        state=state,
        postal_code=postal_code,
        country=country,
        latitude=latitude,
        longitude=longitude,
        phone=phone,
        website=website,
        google_url=google_url,
        rating=rating,
        user_ratings_total=user_ratings_total,
        types=types,
        owner_id=user.id,
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)

    # Redirect to the new company's dashboard
    return RedirectResponse(f"/dashboard/{comp.id}", status_code=302)
