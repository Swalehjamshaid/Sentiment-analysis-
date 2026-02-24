from __future__ import annotations

import os
import logging
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
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

logger.info(f"Dashboard Route Module Loaded. Templates path: {TEMPLATE_DIR}")

# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def render_dashboard(request: Request, db: Session = Depends(get_db)):
    """Renders the Unified Dashboard."""
    try:
        company_count = db.query(Company).count()
        review_count = db.query(Review).count()

        logger.info(f"Dashboard accessed. Stats: {company_count} companies, {review_count} reviews.")

        return templates.TemplateResponse(
            "dashboard.html",
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading the dashboard interface. Check {TEMPLATE_DIR}"
        )

@router.get("/api/dashboard/stats")
async def get_global_stats(db: Session = Depends(get_db)):
    """Lightweight API endpoint for dashboard metrics."""
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
    template_path = os.path.join(TEMPLATE_DIR, "dashboard.html")
    exists = os.path.exists(template_path)
    
    if not exists:
        logger.warning(f"Template NOT FOUND at: {template_path}")
    else:
        logger.info("Dashboard template verified.")

log_dashboard_init()
