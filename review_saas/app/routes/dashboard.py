
# filename: app/routes/dashboard.py
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates

from app.core.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _require_auth(request: Request):
    if not request.session.get("user_id"):
        return RedirectResponse(url=f"/login?next=/dashboard", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": f"{settings.APP_NAME} — Dashboard",
        },
    )


@router.get("/api/kpis")
async def api_kpis():
    return {"total_reviews": 0, "avg_sentiment": 0.0, "new_reviews": 0}


@router.get("/api/orders/series")
async def api_orders_series(days: int = 14):
    series = [{"date": f"day-{i}", "value": i % 5} for i in range(days)]
    return {"series": series}


@router.get("/api/category-mix")
async def api_category_mix():
    return {"categories": [{"name": "Service", "value": 40}, {"name": "Food", "value": 60}]}


@router.get("/api/activity")
async def api_activity(limit: int = 50):
    return {"items": []}
