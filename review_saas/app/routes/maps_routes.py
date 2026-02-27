
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from app.utils.google_maps_client import get_api_key, geocode_address, get_distance

router = APIRouter(prefix="/maps", tags=["maps"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/show_map")
def show_map(request: Request):
    api_key = get_api_key()
    return templates.TemplateResponse(
        "map.html",
        {"request": request, "api_key": api_key}
    )

@router.get("/geocode")
def get_geocode(address: str):
    result = geocode_address(address)
    return result if result else {"error": "Address not found"}

@router.get("/distance")
def distance(origin: str, destination: str):
    result = get_distance(origin, destination)
    return result if result else {"error": "Distance data not found"}
