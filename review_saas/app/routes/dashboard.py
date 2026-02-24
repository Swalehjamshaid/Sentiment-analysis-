from __future__ import annotations
import logging
from typing import Dict, Any

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

# Internal imports from your project structure
from ..db import get_db
from ..models import Company, Review

# 1. Setup Logging & Router
logger = logging.getLogger("dashboard")
router = APIRouter(tags=["dashboard"])

# 2. Configure Templates
# Ensure the directory matches your structure: app/templates/
templates = Jinja2Templates(directory="app/templates")

# 3. Dashboard View Route
@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request, db: Session = Depends(get_db)):
    """
    Renders the Unified Executive Dashboard.
    
    Flow:
    1. Fetch high-level counts for the header.
    2. Pass the 'request' object (required by Jinja2).
    3. Return the 'dashbord.html' template.
    """
    try:
        # Fetch basic portfolio stats for initial load
        company_count = db.query(Company).count()
        review_count = db.query(Review).count()

        # Build context dictionary
        context = {
            "request": request,
            "stats": {
                "total_companies": company_count,
                "total_reviews": review_count,
                "system_date": "2026-02-24"
            }
        }

        # IMPORTANT: Ensure the filename matches your file exactly (dashbord.html)
        return templates.TemplateResponse("dashbord.html", context)

    except Exception as e:
        logger.error(f"Failed to load dashboard: {str(e)}")
        # If the template is missing, this provides a clear error in the logs
        raise HTTPException(status_code=500, detail="Dashboard template initialization failed.")

# 4. Optional: API Health Check for Dashboard
@router.get("/api/dashboard/status")
async def get_dashboard_status(db: Session = Depends(get_db)):
    """Backend status check specifically for dashboard data availability."""
    return {
        "status": "online",
        "database_connected": True,
        "company_entries": db.query(Company).count()
    }
