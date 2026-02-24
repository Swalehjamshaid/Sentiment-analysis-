from __future__ import annotations
import os
import logging
from typing import Dict, Any

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

# Internal imports
from ..db import get_db
from ..models import Company, Review

# 1. Setup Logging & Router
logger = logging.getLogger("dashboard")
router = APIRouter(tags=["dashboard"])

# 2. Dynamic Template Path Discovery
# This finds the absolute path to the templates folder to fix Railway "Not Found" errors
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
    
    Flow:
    1. Fetch high-level portfolio counts (Companies & Reviews).
    2. Pass the 'request' object for Jinja2 rendering.
    3. Serve 'dashbord.html' from the absolute template path.
    """
    try:
        # Fetch actual DB counts for the dashboard header
        company_count = db.query(Company).count()
        review_count = db.query(Review).count()

        # Build context for Jinja2
        context = {
            "request": request,
            "stats": {
                "total_companies": company_count,
                "total_reviews": review_count,
                "system_date": "2026-02-24"
            }
        }

        # IMPORTANT: Ensure the filename on your disk is 'dashbord.html'
        return templates.TemplateResponse("dashbord.html", context)

    except Exception as e:
        logger.error(f"Failed to load dashboard: {str(e)}")
        # If the file is missing, this raises a clear error in Railway logs
        raise HTTPException(
            status_code=500, 
            detail=f"Dashboard template error. Check if 'dashbord.html' exists in {TEMPLATE_DIR}"
        )

# 4. API Health Check for Dashboard
@router.get("/api/dashboard/status")
async def get_dashboard_status(db: Session = Depends(get_db)):
    """Backend status check specifically for dashboard data availability."""
    return {
        "status": "online",
        "database_connected": True,
        "company_entries": db.query(Company).count(),
        "server_time": "2026-02-24T09:45:00Z"
    }
