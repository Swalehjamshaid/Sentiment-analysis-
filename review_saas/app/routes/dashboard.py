# FILE: app/routes/dashboard.py
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..services.rbac import get_current_user  # ensures user is loaded or 401

# Try to use templates if available; otherwise fall back to JSON.
try:
    from fastapi.templating import Jinja2Templates
    # Adjust this path if your templates live elsewhere
    templates = Jinja2Templates(directory="app/templates")
except Exception:
    templates = None

router = APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Renders the dashboard for the authenticated user.
    Fixes:
      - Avoids NoneType.id crash by enforcing auth via get_current_user.
      - Replaces invalid SQLAlchemy filter that mixed a boolean with a SQL expression.
    """
    # Defensive guard (in case get_current_user implementation ever returns None)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    user_role = getattr(current_user, "role", "user")

    # Build query based on role instead of mixing Python boolean into SQLAlchemy filter.
    if user_role == "admin":
        companies_q = db.query(models.Company)
    else:
        # Owners/Managers/Analysts can see only their companies (adjust if you have a mapping table).
        companies_q = db.query(models.Company).filter(models.Company.owner_id == current_user.id)

    companies = companies_q.order_by(models.Company.created_at.desc()).all()

    context = {
        "request": request,
        "user": current_user,
        "user_role": user_role,
        "companies": companies,
    }

    # Prefer template render; fallback to JSON if templates not configured.
    if templates:
        return templates.TemplateResponse("dashboard.html", context)
    return JSONResponse(content=context, status_code=200)
