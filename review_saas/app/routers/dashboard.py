# filename: app/routers/dashboard.py
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")

@router.get('/dashboard')
async def dashboard(request: Request):
    totals = {"total_reviews": 0, "avg_rating": 0}
    chart = {"labels": ["Jan","Feb","Mar"], "values": [4.2,4.3,4.1]}
    return templates.TemplateResponse('dashboard.html', {"request": request, "totals": totals, "chart": chart})
