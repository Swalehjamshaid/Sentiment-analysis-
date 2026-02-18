# Filename: app/utils/google_maps_client.py

import os
import googlemaps
from datetime import datetime
from typing import Optional, Dict, Any

# Fetch the Google Maps API key from environment variable
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
if not GOOGLE_MAPS_API_KEY:
    raise ValueError("GOOGLE_MAPS_API_KEY is not set in environment variables")

# Initialize the Google Maps client
gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

def geocode_address(address: str) -> Optional[Dict[str, Any]]:
    """
    Fetch geocoding data for a given address.
    Returns the first result if found.
    """
    results = gmaps.geocode(address)
    if results:
        return results[0]
    return None

def get_place_details(place_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch place details using place_id.
    """
    result = gmaps.place(place_id=place_id)
    if result.get("result"):
        return result["result"]
    return None

def get_distance(origin: str, destination: str) -> Optional[Dict[str, Any]]:
    """
    Fetch distance matrix info between origin and destination.
    """
    result = gmaps.distance_matrix(origins=[origin], destinations=[destination])
    if result.get("rows"):
        return result["rows"][0]["elements"][0]
    return None

def get_directions(origin: str, destination: str) -> Optional[Dict[str, Any]]:
    """
    Fetch directions between origin and destination.
    """
    directions = gmaps.directions(origin, destination, departure_time=datetime.now())
    if directions:
        return directions[0]
    return None

def get_api_key() -> str:
    """
    Return the Google Maps API key for use in HTML templates.
    """
    return GOOGLE_MAPS_API_KEY
