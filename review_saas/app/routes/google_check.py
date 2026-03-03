# filename: app/core/google_check.py
from googlemaps import Client
from app.core.config import settings
import requests
import logging

# Set up logging to see this clearly in Railway logs
logger = logging.getLogger(__name__)

def verify_google_apis():
    """
    Verify Google Places, Maps, and Business APIs.
    Improved version with better error reporting and connectivity checks.
    """
    # 1. Check if keys even exist in Environment Variables
    keys_to_check = {
        "PLACES": settings.GOOGLE_PLACES_API_KEY,
        "MAPS": settings.GOOGLE_MAPS_API_KEY,
        "BUSINESS": settings.GOOGLE_BUSINESS_API_KEY
    }
    
    for name, key in keys_to_check.items():
        if not key or key == "your_key_here":
            print(f"⚠️ CONFIG ERROR: {name} API Key is missing in Railway Variables.")

    try:
        # Google Places API check
        if settings.GOOGLE_PLACES_API_KEY:
            gmaps_places = Client(key=settings.GOOGLE_PLACES_API_KEY, timeout=10)
            # Searching for a specific known entity to verify data flow
            places_result = gmaps_places.places(query="Haier Lahore")
            
            if places_result.get("status") == "OK":
                print("✅ Google Places API is working and returning data.")
            elif places_result.get("status") == "REQUEST_DENIED":
                print(f"❌ Google Places API Denied: {places_result.get('error_message')}")
            else:
                print(f"⚠️ Google Places API status: {places_result.get('status')}. (Check if Billing is enabled).")

        # Google Maps API check
        if settings.GOOGLE_MAPS_API_KEY:
            gmaps_maps = Client(key=settings.GOOGLE_MAPS_API_KEY, timeout=10)
            maps_result = gmaps_maps.geocode("Lahore, Pakistan")
            if maps_result:
                print("✅ Google Maps API is working.")
            else:
                print("⚠️ Google Maps API returned no results for Lahore.")

        # Google Business API check
        if settings.GOOGLE_BUSINESS_API_KEY:
            business_url = f"https://mybusinessbusinessinformation.googleapis.com/v1/accounts?key={settings.GOOGLE_BUSINESS_API_KEY}"
            resp = requests.get(business_url, timeout=10)
            if resp.status_code == 200:
                print("✅ Google Business API is working.")
            elif resp.status_code == 403:
                print("⚠️ Google Business API: Access Denied (Check if API is enabled in Cloud Console).")
            else:
                print(f"⚠️ Google Business API returned status code {resp.status_code}.")

    except Exception as e:
        # This catches the 'Network is unreachable' error specifically
        print(f"❌ Google API connectivity check failed: {str(e)}")
        if "101" in str(e):
            print("👉 HINT: This is a network error. Check Railway outbound rules or API Key restrictions.")
