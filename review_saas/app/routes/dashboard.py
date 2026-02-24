from __future__ import annotations
import os
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

# 2. Dynamic Template Path Discovery (Permanent Rule)
# This rule calculates the absolute path to /app/templates relative to this file's location.
# It prevents the "/app/app/templates" mismatch seen in Railway logs.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

templates = Jinja2Templates(directory=TEMPLATE_DIR)
logger.info(f"Dashboard Route Module Loaded. Templates path: {TEMPLATE_DIR}")

# 3. Dashboard View Route
@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request, db: Session = Depends(get_db)):
    """
    Renders the Unified Executive Dashboard for Huda.
    """
    try:
        # Fetch current portfolio data for the dashboard header
        company_count = db.query(Company).count()
        review_count = db.query(Review).count()

        context = {
            "request": request,
            "stats": {
                "total_companies": company_count,
                "total_reviews": review_count,
                "system_date": "2026-02-24"
            }
        }

        # RULE: Filename corrected to 'dashboard.html' (with the 'a') 
        # to match your physical file: review_saas/app/templates/dashboard.html
        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logger.error(f"Failed to load dashboard template: {str(e)}")
        # If the file is missing, this provides the exact path searched in your Railway logs
        raise HTTPException(
            status_code=500, 
            detail=f"Template Error. Ensure 'dashboard.html' exists in {TEMPLATE_DIR}"
        )

# 4. API Health Check for Dashboard
@router.get("/api/dashboard/status")
async def get_dashboard_status(db: Session = Depends(get_db)):
    return {
        "status": "online",
        "database_connected": True,
        "company_entries": db.query(Company).count(),
        "server_time": "2026-02-24T10:11:00Z"
    }
