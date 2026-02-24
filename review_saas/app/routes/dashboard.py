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
# We use absolute paths to ensure Railway finds the folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

templates = Jinja2Templates(directory=TEMPLATE_DIR)

# 3. Dashboard View Route
@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request, db: Session = Depends(get_db)):
    try:
        # Fetch stats for the UI
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

        # THE CRITICAL FIX: Changed 'dashbord.html' to 'dashboard.html'
        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logger.error(f"Failed to load dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail="Dashboard template error.")
