from __future__ import annotations

import os
import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

# Internal relative imports 
# Note: Adjust these if your folder structure differs
from ..db import get_db
from ..models import Company, Review

# ─────────────────────────────────────────────────────────────
# Logger Configuration
# ─────────────────────────────────────────────────────────────
logger = logging.getLogger("dashboard")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────
# Router & Template Config
# ─────────────────────────────────────────────────────────────
router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")

# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def render_dashboard(
    request: Request, 
    db: Session = Depends(get_db)
):
    """
    Renders the Unified Dashboard (dashbord.html).
    This serves as the primary UI entry point.
    """
    try:
        # Pre-fetch basic stats for initial page load if needed
        company_count = db.query(Company).count()
        review_count = db.query(Review).count()

        logger.info(f"Dashboard accessed. Stats: {company_count} companies, {review_count} reviews.")

        return templates.TemplateResponse(
            "dashbord.html", 
            {
                "request": request,
                "initial_stats": {
                    "companies": company_count,
                    "reviews": review_count
                }
            }
        )
    except Exception as e:
        logger.error(f"Critical error rendering dashboard: {str(e)}")
        # Provide a graceful fallback or error page
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error loading the dashboard interface."
        )

@router.get("/api/dashboard/stats")
async def get_global_stats(db: Session = Depends(get_db)):
    """
    A lightweight API endpoint specifically for dashboard-wide metrics.
    """
    company_count = db.query(Company).count()
    review_count = db.query(Review).count()
    
    return {
        "total_companies": company_count,
        "total_reviews": review_count,
        "system_status": "operational",
        "timestamp": os.getloadavg() if hasattr(os, 'getloadavg') else "N/A"
    }

# ─────────────────────────────────────────────────────────────
# Startup Diagnostic
# ─────────────────────────────────────────────────────────────
def log_dashboard_init():
    """Confirms the dashboard route module is active on startup."""
    template_path = os.path.join(os.getcwd(), "app/templates/dashbord.html")
    exists = os.path.exists(template_path)
    
    logger.info("Dashboard Route Module Loaded.")
    if not exists:
        logger.warning(f"Template NOT FOUND at: {template_path}. Ensure file is named 'dashbord.html'.")
    else:
        logger.info("Dashboard template verified.")

log_dashboard_init()
