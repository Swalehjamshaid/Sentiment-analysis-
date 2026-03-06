import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from app.core.db import get_session
from app.core.models import Company, Review
from app.core.config import settings
from app.services.google_reviews import ingest_company_reviews

router = APIRouter(tags=['dashboard'])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)

@router.get("/dashboard", response_class=HTMLResponse)
async def show_dashboard(request: Request, company_id: int = None):
    """
    Main Dashboard View.
    Displays company stats and the full list of scraped reviews.
    """
    async with get_session() as session:
        # 1. Fetch all companies for the dropdown
        company_res = await session.execute(select(Company).order_by(Company.name))
        all_companies = company_res.scalars().all()

        if not company_id and all_companies:
            company_id = all_companies[0].id

        if not company_id:
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "companies": [],
                "selected_company": None,
                "reviews": [],
                "stats": {"total": 0, "avg_rating": 0}
            })

        # 2. Fetch Selected Company and Stats
        selected_company = await session.get(Company, company_id)
        
        # Count total reviews in DB for this company
        total_stmt = select(func.count()).select_from(Review).where(Review.company_id == company_id)
        avg_stmt = select(func.avg(Review.rating)).where(Review.company_id == company_id)
        
        total_reviews = (await session.execute(total_stmt)).scalar() or 0
        avg_rating = round(float((await session.execute(avg_stmt)).scalar() or 0), 2)

        # 3. Fetch latest reviews (No longer limited to 5)
        review_stmt = (
            select(Review)
            .where(Review.company_id == company_id)
            .order_by(Review.google_review_time.desc())
            .limit(100)
        )
        reviews = (await session.execute(review_stmt)).scalars().all()

        stats = {
            "total": total_reviews,
            "avg_rating": avg_rating
        }

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "companies": all_companies,
        "selected_company": selected_company,
        "reviews": reviews,
        "stats": stats
    })

@router.post("/dashboard/fetch")
async def trigger_fetch(company_id: int, place_id: str):
    """
    Triggered by the 'Fetch Data' button.
    Calls Outscapter to get a full review set.
    """
    try:
        # Use the ingestion service which is now configured for Outscapter
        await ingest_company_reviews(place_id=place_id, company_id=company_id)
        
        # Update last synced time on the company record
        async with get_session() as session:
            company = await session.get(Company, company_id)
            if company:
                company.last_synced_at = func.now()
                await session.commit()

        return RedirectResponse(url=f"/dashboard?company_id={company_id}", status_code=303)
    
    except Exception as e:
        logger.error(f"Manual fetch failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to sync with Outscapter")
