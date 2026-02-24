# File: review_saas/app/routes/dashboard.py
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

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

# More reliable path calculation using pathlib
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
    Renders the Unified Dashboard.

    Template used: dashboard.html
    Expected location: review_saas/app/templates/dashboard.html
    """
    # Optional: protect route (uncomment when you have auth)
    # if not current_user:
    #     return RedirectResponse(url="/login")

    try:
        company_count = db.query(Company).count()
        review_count = db.query(Review).count()

        logger.info(f"Dashboard accessed. Stats: {company_count} companies, {review_count} reviews.")

        return templates.TemplateResponse(
            "dashboard.html",  # Correct filename - no typo
            {
                "request": request,
                # "current_user": current_user,          # ← uncomment when ready
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
            detail=f"Error loading dashboard. Template path: {TEMPLATE_DIR}"
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
# Startup Diagnostic (only once at startup)
# ─────────────────────────────────────────────────────────────
def log_dashboard_init():
    """
    Verifies that dashboard.html exists at startup.
    Uses pathlib for more reliable path handling.
    """
    template_file = TEMPLATE_DIR / "dashboard.html"
    
    if template_file.exists() and template_file.is_file():
        logger.info(f"Dashboard template verified at: {template_file}")
    else:
        logger.warning(
            f"Template NOT FOUND at: {template_file}. "
            f"Make sure the file is named exactly 'dashboard.html' "
            f"(lowercase, with 'a' after 'dashbo')."
        )

# Run diagnostic once when module is imported
log_dashboard_init()
