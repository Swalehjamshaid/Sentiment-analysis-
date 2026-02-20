# File: app/routes/dashboard.py
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Company
# from ..auth import get_current_user  # Uncomment when auth is ready

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/", name="dashboard")
@router.get("/{company_id}", name="dashboard_with_company")
async def get_dashboard(
    request: Request,
    company_id: int | None = None,
    db: Session = Depends(get_db),
    # current_user = Depends(get_current_user)  # Uncomment later
):
    """
    Render the main dashboard page.
    Optionally pre-select a company if company_id is provided in URL.
    """
    # Optional: filter by user when auth is added
    # companies = db.query(Company).filter(Company.user_id == current_user.id).all()

    # For now: show all companies (or change to user-specific)
    initial_company = None
    if company_id:
        initial_company = db.query(Company).filter(Company.id == company_id).first()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "current_company_id": company_id or 0,
            "company_name": initial_company.name if initial_company else None
        }
    )
