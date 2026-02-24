from __future__ import annotations

import os
import logging
from typing import Dict, Any

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

# Internal relative imports
from ..db import get_db
from ..models import Company, Review

# ───────────────────────────────────────────────
# Logger Configuration
# ───────────────────────────────────────────────
logger = logging.getLogger("dashboard")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ───────────────────────────────────────────────
# Router & Template Config
# ───────────────────────────────────────────────
router = APIRouter(tags=["dashboard"])
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # → review_saas/app
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

logger.info(f"Dashboard module loaded → template directory: {TEMPLATE_DIR}")

# ───────────────────────────────────────────────
# Dashboard Routes
# ───────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def render_dashboard(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Renders the main dashboard page using dashboard.html
    """
    try:
        company_count = db.query(Company).count()
        review_count = db.query(Review).count()

        logger.info(f"Dashboard accessed. Stats: {company_count} companies, {review_count} reviews.")

        return templates.TemplateResponse(
            "dashboard.html",  # ✅ Correct filename
            {
                "request": request,
                "initial_stats": {
                    "companies": company_count,
                    "reviews": review_count
                }
            }
        )
    except Exception as e:
        logger.error(f"Critical error rendering dashboard: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error loading the dashboard interface."
        )

# ───────────────────────────────────────────────
# Redirect old /dashbord URLs → /dashboard
# ───────────────────────────────────────────────
@router.get("/dashbord", response_class=HTMLResponse)
@router.get("/dashbord.html", response_class=HTMLResponse)
async def redirect_legacy_dashboard():
    """
    Redirect legacy /dashbord URL requests to /dashboard
    """
    logger.warning("Redirecting legacy /dashbord request → /dashboard")
    return RedirectResponse(url="/dashboard")

# ───────────────────────────────────────────────
# API Stats Endpoint
# ───────────────────────────────────────────────
@router.get("/api/dashboard/stats")
async def get_global_stats(db: Session = Depends(get_db)):
    """
    Returns lightweight JSON metrics for the dashboard
    """
    company_count = db.query(Company).count()
    review_count = db.query(Review).count()

    return {
        "total_companies": company_count,
        "total_reviews": review_count,
        "system_status": "operational",
        "timestamp": os.getloadavg() if hasattr(os, 'getloadavg') else "N/A"
    }

# ───────────────────────────────────────────────
# Startup Diagnostic
# ───────────────────────────────────────────────
def log_dashboard_init():
    """Confirm dashboard template exists at startup"""
    template_path = os.path.join(TEMPLATE_DIR, "dashboard.html")
    if os.path.exists(template_path):
        logger.info(f"Dashboard template verified → {template_path}")
    else:
        logger.warning(f"Dashboard template NOT FOUND → {template_path}")

log_dashboard_init()
