
# filename: app/services/google_places.py
from __future__ import annotations
import googlemaps  # type: ignore
from typing import Dict, Any
from app.core.config import settings

def client() -> 'googlemaps.Client':
    if not settings.GOOGLE_MAPS_API_KEY:
        raise RuntimeError('GOOGLE_MAPS_API_KEY missing')
    return googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)

def place_details(place_id: str) -> Dict[str, Any]:
    gm = client()
    return gm.place(place_id=place_id)
