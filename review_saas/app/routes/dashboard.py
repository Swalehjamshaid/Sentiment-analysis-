# File: review_saas/app/routes/dashboard.py
from __future__ import annotations

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
BASE_DIR = Path(__file__).resolve().parent.parent      # → review_saas/app
TEMPLATE_DIR = BASE_DIR / "templates"                   # → review_saas/app/templates

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

logger.info(f"Dashboard module loaded → template directory: {TEMPLATE_DIR}")

# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def render_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    # current_user = Depends(get_current_user)   # ← activate when auth is ready
):
    """
    Renders the main dashboard page using dashboard.html
    """
    try:
        company_count = db.query(Company).count()
        review_count = db.query(Review).count()

        logger.info(f"Dashboard loaded → {company_count} companies, {review_count} reviews")

        return templates.TemplateResponse(
            "dashboard.html",   # ← correct filename (this line renders the template)
            {
                "request": request,
                # "current_user": current_user,        # ← activate when ready
                "initial_stats": {
                    "companies": company_count,
                    "reviews": review_count
                }
            }
        )

    except Exception as e:
        logger.error(f"Dashboard render failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cannot render dashboard. Template folder: {TEMPLATE_DIR}"
        )


@router.get("/api/dashboard/stats")
async def get_global_stats(db: Session = Depends(get_db)):
    """
    Simple JSON stats endpoint (used by frontend if needed)
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
# One-time startup check (runs when module is imported)
# ─────────────────────────────────────────────────────────────
def check_dashboard_template():
    """
    Startup diagnostic: confirm dashboard.html exists
    """
    file_path = TEMPLATE_DIR / "dashboard.html"

    if file_path.is_file():
        logger.info(f"Dashboard template OK → {file_path}")
    else:
        logger.warning(f"Missing dashboard template → {file_path}")
        logger.warning("Expected: review_saas/app/templates/dashboard.html")


# Run check once
check_dashboard_template()
