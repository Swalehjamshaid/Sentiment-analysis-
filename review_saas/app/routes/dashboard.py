# File: app/routes/dashboard.py
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Any

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Company
from app.routes.companies import get_dashboard_data

router = APIRouter(tags=["dashboard"])

@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard_page(
    request: Request, 
    company_id: int = None,
    db: Session = Depends(get_db), 
    current_user: Any = Depends(get_current_user)
):
    from app.main import templates, common_context
    
    try:
        # Fetches analytics data
        dashboard_payload = get_dashboard_data(db, company_id)
        
        selected_company = None
        if company_id:
            selected_company = db.query(Company).filter(Company.id == company_id).first()

        context = common_context(request)
        context.update({
            "dashboard_payload": dashboard_payload,
            "selected_company": selected_company
        })
        
        return templates.TemplateResponse("dashboard.html", context)
    except Exception:
        raise HTTPException(status_code=500, detail="Error loading the dashboard interface.")
