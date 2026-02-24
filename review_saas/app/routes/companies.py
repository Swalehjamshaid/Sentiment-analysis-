# File: app/routes/companies.py
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
# ✅ FIXED: Now importing from dependencies.py to avoid circular import
from app.dependencies import get_current_user 

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])

# Setup templates relative to this file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

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

@router.get("/dashbord", response_class=HTMLResponse)
async def redirect_legacy_dashboard():
    return RedirectResponse(url="/dashboard")

@router.get("/api/dashboard/stats")
async def get_global_stats(db: Session = Depends(get_db)):
    company_count = db.query(Company).count()
    review_count = db.query(Review).count()
    return {
        "total_companies": company_count,
        "total_reviews": review_count,
        "system_status": "operational"
    }
