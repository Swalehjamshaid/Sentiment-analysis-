# filename: app/routes/companies.py
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from ..core.db import get_db
from ..models.models import Company, Review, User
from ..services.google_reviews import google_api
# FIXED: Importing from the actual location in app/core/
from ..core.security import get_current_user 

logger = logging.getLogger('app.companies')
router = APIRouter(prefix="/companies", tags=["Company Management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/add", response_class=HTMLResponse)
async def add_company_page(request: Request, current_user: User = Depends(get_current_user)):
    """Requirement #33: Page to add a new business."""
    return templates.TemplateResponse("companies.html", {"request": request, "user": current_user})

@router.post("/add")
async def add_company(
    request: Request,
    place_id: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Requirement #42: Owner tracking
):
    # Requirement #38: Duplicate Check (Prevent adding the same company twice for one user)
    existing = db.query(Company).filter(
        Company.place_id == place_id, 
        Company.owner_id == current_user.id
    ).first()
    
    if existing:
        return templates.TemplateResponse("companies.html", {
            "request": request, 
            "error": "You are already tracking this business.",
            "user": current_user
        })

    # Requirement #35: Validate via Google API
    details = google_api.validate_business(place_id)
    if not details:
        return templates.TemplateResponse("companies.html", {
            "request": request, 
            "error": "Invalid Google Place ID. Please verify and try again.",
            "user": current_user
        })

    # Requirement #33: Save Company Data (Points 41-48)
    new_company = Company(
        owner_id=current_user.id,
        name=details.get('name'),
        place_id=details.get('place_id'),
        address=details.get('formatted_address'),
        lat=details.get('geometry', {}).get('location', {}).get('lat'),
        lng=details.get('geometry', {}).get('location', {}).get('lng'),
        status="active"
    )
    db.add(new_company)
    db.commit()
    db.refresh(new_company)

    # Requirement #52: Auto-fetch reviews immediately after adding
    raw_reviews = google_api.fetch_latest_reviews(place_id)
    for r in raw_reviews:
        # Requirement #70: Prevent duplicates using Google's timestamp as unique ID
        review_obj = Review(
            company_id=new_company.id,
            external_id=str(r.get('time')),
            text=r.get('text'),
            rating=r.get('rating'),
            reviewer_name=r.get('author_name'),
            reviewer_avatar=r.get('profile_photo_url'),
            review_date=datetime.fromtimestamp(r.get('time'), tz=timezone.utc)
        )
        db.add(review_obj)
    
    db.commit()
    logger.info(f"User {current_user.id} added company {new_company.id}")
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
