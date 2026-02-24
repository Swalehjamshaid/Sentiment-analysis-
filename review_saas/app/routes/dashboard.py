# File: review_saas/app/routes/dashboard.py
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

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

# Reliable path calculation
BASE_DIR = Path(__file__).resolve().parent.parent  # → review_saas/app
TEMPLATE_DIR = BASE_DIR / "templates"               # → review_saas/app/templates

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

logger.info(f"Dashboard Route Module Loaded. Templates path: {TEMPLATE_DIR}")

# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def render_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    # current_user = Depends(get_current_user)  # ← uncomment when auth is ready
):
    """
    Renders the Unified Dashboard using dashboard.html
    
    Expected template location: review_saas/app/templates/dashboard.html
    """
    try:
        company_count = db.query(Company).count()
        review_count = db.query(Review).count()

        logger.info(f"Dashboard accessed. Stats: {company_count} companies, {review_count} reviews.")

        return templates.TemplateResponse(
            "dashboard.html",  # Correct filename
            {
                "request": request,
                # "current_user": current_user,          # ← uncomment when auth ready
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
            detail=f"Error loading dashboard. Template directory: {TEMPLATE_DIR}"
        )


@router.get("/api/dashboard/stats")
async def get_global_stats(db: Session = Depends(get_db)):
    """
    Lightweight API endpoint for dashboard metrics (JSON).
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
# Startup Diagnostic (runs once when module is imported)
# ─────────────────────────────────────────────────────────────
def log_dashboard_init():
    """
    One-time check at startup: verify dashboard.html exists.
    """
    template_file = TEMPLATE_DIR / "dashboard.html"
    
    if template_file.is_file():
        logger.info(f"Dashboard template found and verified: {template_file}")
    else:
        logger.warning(f"Dashboard template MISSING: {template_file}")
        logger.warning("Expected exact filename: dashboard.html (lowercase)")


# Execute the check once
log_dashboard_init()
