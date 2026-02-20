# File: app/routes/dashboard.py
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Company
# from ..auth import get_current_user  # Uncomment when authentication is ready

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
    """
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
