from __future__ import annotations
import os
import logging
from typing import Any

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

# ───────────────────────────────────────────────
# Corrected imports
# ───────────────────────────────────────────────
from app.db import get_db
from app.models import Company, Review
from app.routes.auth import get_current_user      # ← FIXED: correct path

# ───────────────────────────────────────────────
# Logger Configuration
# ───────────────────────────────────────────────
logger = logging.getLogger(__name__)  # better to use __name__ here
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ───────────────────────────────────────────────
# Router & Template Config
# ───────────────────────────────────────────────
router = APIRouter(tags=["dashboard"])

# More reliable way to locate templates (relative to project structure)
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
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    try:
        company_count = db.query(Company).count()
        review_count = db.query(Review).count()

        user_email = getattr(current_user, "email", "anonymous")
        logger.info(f"Dashboard accessed by {user_email}. Stats: {company_count} companies, {review_count} reviews.")

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "current_user": current_user,
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
# Redirect legacy /dashbord URLs → /dashboard
# ───────────────────────────────────────────────
@router.get("/dashbord", response_class=HTMLResponse)
@router.get("/dashbord.html", response_class=HTMLResponse)
async def redirect_legacy_dashboard():
    logger.warning("Redirecting legacy /dashbord request → /dashboard")
    return RedirectResponse(url="/dashboard")

# ───────────────────────────────────────────────
# API Stats Endpoint
# ───────────────────────────────────────────────
@router.get("/api/dashboard/stats")
async def get_global_stats(db: Session = Depends(get_db)):
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
    template_path = os.path.join(TEMPLATE_DIR, "dashboard.html")
    if os.path.exists(template_path):
        logger.info(f"Dashboard template verified → {template_path}")
    else:
        logger.warning(f"Dashboard template NOT FOUND → {template_path}")

log_dashboard_init()
