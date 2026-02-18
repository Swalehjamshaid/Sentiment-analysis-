# Filename: app/routes/maps_routes.py

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from app.utils.google_maps_client import get_api_key, geocode_address, get_distance

router = APIRouter(prefix="/maps", tags=["maps"])
templates = Jinja2Templates(directory="app/templates")

# Route to render Google Map in HTML template
@router.get("/show_map")
def show_map(request: Request):
    """
    Render a template with the Google Maps API key for JS usage.
    """
    api_key = get_api_key()
    return templates.TemplateResponse(
        "map.html",
        {"request": request, "api_key": api_key}
    )

# Route to get geocode data via API
@router.get("/geocode")
def get_geocode(address: str):
    """
    Fetch geocode data for the given address.
    """
    result = geocode_address(address)
    return result if result else {"error": "Address not found"}

# Route to get distance between origin and destination
@router.get("/distance")
def distance(origin: str, destination: str):
    """
    Fetch distance info between origin and destination.
    """
    result = get_distance(origin, destination)
    return result if result else {"error": "Distance data not found"}
