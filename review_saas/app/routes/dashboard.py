# filename: app/services/dashboard.py
from __future__ import annotations
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.models import Company
from app.core.database import get_db
from app.services.google_reviews import GoogleReviewsService
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")  # adjust path

@router.get("/dashboard/{company_id}", response_class=HTMLResponse)
async def dashboard_view(request: Request, company_id: int, db: AsyncSession = Depends(get_db)):
    company = await db.get(Company, company_id)
    if not company:
        return HTMLResponse(content="Company not found", status_code=404)

    review_service = GoogleReviewsService(db)

    # Fetch Google Place reviews
    place_reviews = []
    if company.place_id:
        place_reviews = await review_service.fetch_place_reviews(company.place_id)

    # Fetch Google Business reviews
    business_reviews = []
    if hasattr(company, "business_account_id") and company.business_account_id:
        business_reviews = await review_service.fetch_business_reviews(company.business_account_id)

    # Combine reviews and save
    all_reviews = place_reviews + business_reviews
    if all_reviews:
        await review_service.save_reviews_to_db(company, all_reviews)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "company": company,
            "reviews": all_reviews,
            "place_reviews_count": len(place_reviews),
            "business_reviews_count": len(business_reviews),
        }
    )
